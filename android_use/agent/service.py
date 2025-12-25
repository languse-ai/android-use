from __future__ import annotations

import asyncio
import logging
import pdb
import time
import traceback
from pathlib import Path
from typing import Awaitable, Callable, Type, Union, Any
import json
from json_repair import repair_json
from android_use.agent.views import AgentSettings, AgentStepInfo, StepMetadata
from android_use.android.context import AndroidContext
from android_use.tools.service import AndroidTools
from android_use.agent.message_manager import MessageManager, MessageManagerSettings, MessageHistory
from android_use.agent.prompts import AgentSystemPrompt, StateMessagePrompt
from android_use.android.views import AndroidState, AndroidStateHistory
from android_use.utils import time_execution_async, time_execution_sync
from android_use.llm.base import BaseChatModel
from android_use.llm import SystemMessage, UserMessage, AssistantMessage, ContentText
from android_use.tokens.service import TokenCost
from android_use.agent.views import ActionResult
from .views import AgentState, AgentOutput, AgentHistoryList, AgentHistory

logger = logging.getLogger(__name__)


class AndroidUseAgent:
    def __init__(
            self,
            agent_settings: AgentSettings,
            llm: BaseChatModel,
            android_context: AndroidContext,
            android_tools: AndroidTools = None,
            message_settings: MessageManagerSettings = None,
            system_prompt_class: Type[AgentSystemPrompt] = AgentSystemPrompt,
            state_message_class: Type[StateMessagePrompt] = StateMessagePrompt,
            message_history: MessageHistory = None,
            register_new_step_callback: Union[
                Callable[['AndroidState', 'AgentOutput', int], None],  # Sync callback
                Callable[['AndroidState', 'AgentOutput', int], Awaitable[None]],  # Async callback
                None,
            ] = None,
            register_done_callback: Union[
                Callable[['AgentHistoryList'], Awaitable[None]],  # Async Callback
                Callable[['AgentHistoryList'], None],  # Sync Callback
                None,
            ] = None,
            register_external_agent_status_raise_error_callback: Callable[[], Awaitable[bool]] | None = None,
    ):
        self.agent_settings = agent_settings
        self.llm = llm
        self.token_cost_service = TokenCost(include_cost=True)
        self.token_cost_service.register_llm(self.llm)
        self.android_context = android_context
        self.android_tools = android_tools or AndroidTools()
        self.system_prompt_class = system_prompt_class
        self.state_message_class = state_message_class
        self.message_manager = MessageManager(
            settings=message_settings or MessageManagerSettings(),
            message_history=message_history
        )
        self.state = AgentState()
        self.task = ""
        # setup Action Model
        self._setup_action_models()

        self.register_new_step_callback = register_new_step_callback
        self.register_done_callback = register_done_callback
        self.register_external_agent_status_raise_error_callback = register_external_agent_status_raise_error_callback

        # Event-based pause control (kept out of AgentState for serialization)
        self._external_pause_event = asyncio.Event()
        self._external_pause_event.set()

    def _setup_action_models(self) -> None:
        """Setup dynamic action models from controller's registry"""
        # Initially only include actions with no filters
        self.ActionModel = self.android_tools.registry.create_action_model()
        # Create output model with the dynamic actions
        self.AgentOutput = AgentOutput.type_with_custom_actions(self.ActionModel)

    def _convert_initial_actions(self, actions: list[dict[str, dict[str, Any]]]):
        """Convert dictionary-based actions to ActionModel instances"""
        converted_actions = []
        action_model = self.ActionModel
        for action_dict in actions:
            # Each action_dict should have a single key-value pair
            action_name = next(iter(action_dict))
            params = action_dict[action_name]

            # Get the parameter model for this action from registry
            action_info = self.android_tools.registry.registry.actions[action_name]
            param_model = action_info.param_model

            # Create validated parameters using the appropriate param model
            validated_params = param_model(**params)

            # Create ActionModel instance with the validated parameters
            action_model = self.ActionModel(**{action_name: validated_params})
            converted_actions.append(action_model)

        return converted_actions

    def pause(self) -> None:
        """Pause the agent before the next step"""
        print('\n\n⏸️ Paused the agent and left the browser open.\n\tPress [Enter] to resume or [Ctrl+C] again to quit.')
        self.state.paused = True
        self._external_pause_event.clear()

    def resume(self) -> None:
        """Resume the agent"""
        print('----------------------------------------------------------------------')
        print('▶️  Resuming agent execution where it left off...\n')
        self.state.paused = False
        self._external_pause_event.set()

    def stop(self) -> None:
        """Stop the agent"""
        logger.info('⏹️ Agent stopping')
        self.state.stopped = True
        
        # Signal pause event to unblock any waiting code so it can check the stopped state
        self._external_pause_event.set()

    def reset(self) -> None:
        """Reset the agent state for a new run"""
        self.state = AgentState()
        self._external_pause_event.set()
        self.task = ""


    async def run(self, task: str, max_steps: int = 100, **kwargs) -> AgentHistoryList:
        """
        Run the Android automation agent.
        
        Args:
            task: The task description for the agent
            max_steps: Maximum number of steps to execute
            **kwargs: Additional arguments
            
        Returns:
            AgentHistoryList: History of all agent actions and results
        """
        self.task = task
        logger.info(f"Starting Android agent with task: {task}")
        logger.info(f"Max steps: {max_steps}")

        # Get event loop for signal handler
        loop = asyncio.get_event_loop()

        # Setup signal handler with pause/resume/stop callbacks
        from android_use.utils import SignalHandler
        signal_handler = SignalHandler(
            loop=loop,
            pause_callback=self.pause,
            resume_callback=self.resume,
            exit_on_second_int=True,
        )
        signal_handler.register()

        # Initialize system prompt
        system_prompt = self.system_prompt_class(
            action_description=self.android_tools.registry.get_prompt_description(),
            max_actions_per_step=self.agent_settings.max_actions_per_step
        )

        # Add system message
        if not self.message_manager.message_history.messages:
            system_message = self.message_manager.create_message(
                role="system",
                text=system_prompt.get_system_message()
            )
            self.message_manager.add_message(system_message)

        # Add task message
        task_message = self.message_manager.create_message(
            role="user",
            text=f"Task: {task}"
        )
        self.message_manager.add_message(task_message)
        response = None
        # Main agent loop
        for step in range(max_steps):
            try:
                step_start_time = time.time()
                logger.info(f"\n{'=' * 60}")
                logger.info(f"Step {step + 1}/{max_steps}")
                logger.info(f"{'=' * 60}")

                # Check if agent is stopped or paused
                if self.state.stopped:
                    logger.info("Agent stopped by external signal")
                    break

                if self.state.paused:
                    logger.info("Agent paused, waiting...")
                    await self._external_pause_event.wait()
                    signal_handler.reset()

                # Step 1: Get Android context
                current_state = self.android_context.update_state()

                # Step 2: Build state message
                step_info = AgentStepInfo(step_number=step, max_steps=max_steps)
                state_message_text, images = self.state_message_class.get_state_message(
                    current_state,
                    step_info,
                    use_vision=self.agent_settings.use_vision
                )

                # Add state message with screenshot
                state_message = self.message_manager.create_message(
                    role="user",
                    text=state_message_text,
                    images=images,
                    image_format="png"
                )
                self.message_manager.add_message(state_message)

                # Limit state messages first
                self.message_manager.limit_state_messages()

                if response is not None:
                    total_input_tokens = response.usage.total_tokens
                    # Check if we need to summarize due to token limit
                    if total_input_tokens > self.agent_settings.max_input_tokens:
                        logger.warning(
                            f"Token limit exceeded: {total_input_tokens} > {self.agent_settings.max_input_tokens}")
                        logger.info("Generating summary to reduce context...")

                        progress_summary_message = self.message_manager.create_message(
                            role="user",
                            text=f"Please generate progress summary according to current screenshot and agent history conversation."
                        )
                        self.message_manager.add_message(progress_summary_message)

                        logger.info("Calling Summary LLM...")
                        input_summary_messages = self.message_manager.get_messages()
                        summary_response = await self.llm.ainvoke(
                            input_summary_messages
                        )
                        logger.info(summary_response.completion)

                        # Rebuild message history: system + task + summary + current state
                        self.message_manager.clear_message_history()

                        # Re-add system message
                        system_message = self.message_manager.create_message(
                            role="system",
                            text=system_prompt.get_system_message()
                        )
                        self.message_manager.add_message(system_message)

                        # Re-add task message
                        self.message_manager.add_message(task_message)

                        # Add summary as assistant message
                        summary_assistant_message = self.message_manager.create_message(
                            role="assistant",
                            text=f"Current progress summary:\n{summary_response.completion}"
                        )
                        self.message_manager.add_message(summary_assistant_message)

                        self.message_manager.add_message(state_message)

                # Step 3: Get LLM response
                logger.info("Calling LLM...")
                input_messages = self.message_manager.get_messages()
                response = await self.llm.ainvoke(
                    input_messages
                )
                print(response.completion)
                try:
                    model_json_output = json.loads(response.completion.replace("```json", "").replace("```", ""))
                except json.decoder.JSONDecodeError:
                    model_json_output = json.loads(
                        repair_json(response.completion.replace("```json", "").replace("```", "")))

                model_output: AgentOutput = AgentOutput(
                    think=model_json_output.get("think", ""),
                    evaluation_previous_goal=model_json_output.get("evaluation_previous_goal", ""),
                    action=self._convert_initial_actions(model_json_output.get("action", [])),
                )
                # Log think and actions
                logger.info(f"\n{'=' * 60}")
                logger.info(f"Agent State:")
                logger.info(f"  Evaluation: {model_output.evaluation_previous_goal}")
                if model_output.think:
                    logger.info(f"  Think: {model_output.think}")
                logger.info(f"\nActions to execute ({len(model_output.action)}):")
                for i, action in enumerate(model_output.action, 1):
                    action_dict = action.model_dump(exclude_none=True)
                    logger.info(f"  {i}. {action_dict}")
                logger.info(f"{'=' * 60}\n")

                # Step 4: Append LLM response to message history (for cache hit)

                assistant_message = self.message_manager.create_message(
                    role="assistant",
                    text=response.completion,
                )
                self.message_manager.add_message(assistant_message)

                # Step 5: Execute actions using multi_act
                try:
                    action_results = await self.android_tools.multi_act(
                        actions=model_output.action,
                        android_context=self.android_context,
                        page_extraction_llm=self.agent_settings.page_extraction_llm
                    )
                    await self.token_cost_service.log_usage_summary()
                    # Log results
                    for i, result in enumerate(action_results):
                        if result.extracted_content:
                            logger.info(f"  Action {i + 1} result: {result.extracted_content}")
                        if result.error:
                            logger.error(f"  Action {i + 1} error: {result.error}")
                        if result.is_done:
                            logger.info(f"Task completed! Success: {result.success}")
                            logger.info(f"Final result: {result.extracted_content}")

                except Exception as e:
                    error_msg = f"Error executing actions: {str(e)}"
                    logger.error(error_msg)
                    logger.error(traceback.format_exc())
                    action_results = [ActionResult(
                        success=False,
                        error=error_msg
                    )]

                # Step 6: Add action results to message history
                result_texts = []
                for i, result in enumerate(action_results):
                    if result.extracted_content:
                        result_texts.append(f"Action {i + 1} result: {result.extracted_content}")
                    if result.error:
                        result_texts.append(f"Action {i + 1} error: {result.error[:200]} ... ")

                if result_texts:
                    result_message = self.message_manager.create_message(
                        role="user",
                        text="\n".join(result_texts)
                    )
                    self.message_manager.add_message(result_message)

                # Step 7: Save to history
                step_end_time = time.time()

                # Create state history
                state_history = AndroidStateHistory(
                    device_id=current_state.device_id,
                    timestamp=current_state.timestamp,
                    element_description=current_state.element_description,
                    xml=current_state.xml,
                    screenshot=current_state.screenshot,
                    highlight_screenshot=current_state.highlight_screenshot,
                    interacted_element=AgentHistory.get_interacted_element(model_output, current_state.selector_map)
                )

                history_item = AgentHistory(
                    model_output=model_output,
                    result=action_results,
                    state=state_history,
                    metadata=StepMetadata(
                        step_start_time=step_start_time,
                        step_end_time=step_end_time,
                        input_tokens=response.usage.total_tokens,
                        step_number=step
                    )
                )

                self.state.history.history.append(history_item)
                self.state.n_steps = step + 1

                # Call step callback if registered
                if self.register_new_step_callback:
                    logger.info(f"Invoking step callback for step {step}")
                    if asyncio.iscoroutinefunction(self.register_new_step_callback):
                        await self.register_new_step_callback(current_state, model_output, step)
                    else:
                        self.register_new_step_callback(current_state, model_output, step)
                    logger.info(f"Step callback completed for step {step}")

                # Check if task is done
                if any(result.is_done for result in action_results):
                    logger.info("Task marked as done, stopping agent loop")
                    break

            except Exception as e:
                logger.error(f"Error in step {step + 1}: {str(e)}")
                logger.error(traceback.format_exc())
                self.state.consecutive_failures += 1

                if self.state.consecutive_failures >= self.agent_settings.max_failures:
                    logger.error(f"Max failures ({self.agent_settings.max_failures}) reached, stopping")
                    break

                # Add error to message history
                error_message = self.message_manager.create_message(
                    role="user",
                    text=f"Error occurred: {str(e)}. Please try a different approach."
                )
                self.message_manager.add_message(error_message)
            finally:
                self.reset()

        # Generate GIF if requested
        if self.agent_settings.generate_gif:
            try:
                from android_use.agent.gif import create_history_gif

                if isinstance(self.agent_settings.generate_gif, str):
                    gif_path = self.agent_settings.generate_gif
                else:
                    gif_path = "agent_history.gif"

                logger.info(f"Generating GIF at {gif_path}...")
                create_history_gif(
                    task=self.task,
                    history=self.state.history,
                    output_path=gif_path
                )
                logger.info(f"GIF generated successfully")
            except Exception as e:
                logger.error(f"Error generating GIF: {str(e)}")

        # Save history if requested
        if self.agent_settings.save_conversation_path:
            try:
                save_path = Path(self.agent_settings.save_conversation_path)
                logger.info(f"Saving conversation history to {save_path}...")
                self.state.history.save_to_file(save_path)
                logger.info(f"History saved successfully")
            except Exception as e:
                logger.error(f"Error saving history: {str(e)}")

        # Call done callback if registered
        if self.register_done_callback:
            logger.info("Invoking done callback")
            if asyncio.iscoroutinefunction(self.register_done_callback):
                await self.register_done_callback(self.state.history)
            else:
                self.register_done_callback(self.state.history)
            logger.info("Done callback completed")

        # Unregister signal handler when done
        signal_handler.unregister()
        logger.info(f"\nAgent completed after {self.state.n_steps} steps")
        logger.info(f"Total duration: {self.state.history.total_duration_seconds():.2f} seconds")
        logger.info(f"Total input tokens: {self.state.history.total_input_tokens()}")

        return self.state.history
