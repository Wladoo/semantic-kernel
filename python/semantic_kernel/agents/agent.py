# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from semantic_kernel.agents.channels.agent_channel import AgentChannel
from semantic_kernel.contents.history_reducer.chat_history_reducer import ChatHistoryReducer
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.kernel_pydantic import KernelBaseModel
from semantic_kernel.prompt_template.kernel_prompt_template import KernelPromptTemplate
from semantic_kernel.prompt_template.prompt_template_base import PromptTemplateBase
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig
from semantic_kernel.utils.experimental_decorator import experimental_class
from semantic_kernel.utils.naming import generate_random_ascii_name
from semantic_kernel.utils.validation import AGENT_NAME_REGEX

if TYPE_CHECKING:
    from semantic_kernel.contents.chat_history import ChatHistory


logger: logging.Logger = logging.getLogger(__name__)


@experimental_class
class Agent(KernelBaseModel):
    """Base abstraction for all Semantic Kernel agents.

    An agent instance may participate in one or more conversations.
    A conversation may include one or more agents.
    In addition to identity and descriptive meta-data, an Agent
    must define its communication protocol, or AgentChannel.

    Attributes:
        name: The name of the agent (optional).
        description: The description of the agent (optional).
        id: The unique identifier of the agent (optional). If no id is provided,
            a new UUID will be generated.
        instructions: The instructions for the agent (optional
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str | None = None
    name: str = Field(default_factory=lambda: f"agent_{generate_random_ascii_name()}", pattern=AGENT_NAME_REGEX)
    instructions: str | None = None
    kernel: Kernel = Field(default_factory=Kernel)
    channel_type: ClassVar[type[AgentChannel] | None] = None
    history_reducer: ChatHistoryReducer | None = None
    arguments: KernelArguments = Field(default_factory=KernelArguments)
    prompt_template: PromptTemplateBase | None = None

    async def reduce_history(self, history: "ChatHistory") -> bool:
        """Perform the reduction on the provided history, returning True if reduction occurred."""
        if self.history_reducer is None:
            return False

        self.history_reducer.messages = history.messages

        reducer = await self.history_reducer.reduce()
        if reducer is not None:
            history.messages.clear()
            history.messages.extend(reducer.messages)
            return True

        return False

    def get_channel_keys(self) -> Iterable[str]:
        """Get the channel keys.

        Returns:
            A list of channel keys.
        """
        if not self.channel_type:
            raise NotImplementedError("Unable to get channel keys. Channel type not configured.")
        yield self.channel_type.__name__

        if self.history_reducer is not None:
            yield self.history_reducer.__class__.__name__
            yield str(self.history_reducer.__hash__)

    async def create_channel(self) -> AgentChannel:
        """Create a channel.

        Returns:
            An instance of AgentChannel.
        """
        if not self.channel_type:
            raise NotImplementedError("Unable to create channel. Channel type not configured.")
        return self.channel_type()

    async def format_instructions(self, kernel: Kernel, arguments: KernelArguments) -> str | None:
        """Format the instructions.

        Args:
            kernel: The kernel instance.
            arguments: The kernel arguments.

        Returns:
            The formatted instructions.
        """
        if self.prompt_template is None:
            if self.instructions is None:
                return None
            self.prompt_template = KernelPromptTemplate(
                prompt_template_config=PromptTemplateConfig(template=self.instructions)
            )
        return await self.prompt_template.render(kernel, arguments)

    def merge_arguments(self, override_args: KernelArguments) -> KernelArguments:
        """Merge the arguments with the override arguments.

        Args:
            override_args: The arguments to override.

        Returns:
            The merged arguments. If both are None, return None.
        """
        # If the agent's arguments are not set, simply return whatever is passed in.
        if not self.arguments:
            return override_args

        # If the override args are not set, keep the current arguments.
        if not override_args:
            return self.arguments

        # Both are not None, so merge with precedence for override_args.
        merged_execution_settings = dict(self.arguments.execution_settings or {})
        merged_execution_settings.update(override_args.execution_settings or {})

        merged_params = dict(self.arguments)
        merged_params.update(override_args)

        return KernelArguments(settings=merged_execution_settings, **merged_params)

    def __eq__(self, other):
        """Check if two agents are equal."""
        if isinstance(other, Agent):
            return (
                self.id == other.id
                and self.name == other.name
                and self.description == other.description
                and self.instructions == other.instructions
                and self.channel_type == other.channel_type
            )
        return False

    def __hash__(self):
        """Get the hash of the agent."""
        return hash((self.id, self.name, self.description, self.instructions, self.channel_type))
