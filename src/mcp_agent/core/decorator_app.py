"""
Decorator-based interface for MCP Agent applications.
Provides a simplified way to create and manage agents using decorators.
"""

from typing import List, Optional, Dict, Callable, TypeVar, Generic, Any
from enum import Enum
import yaml
import argparse
from contextlib import asynccontextmanager

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.context_dependent import ContextDependent
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.config import Settings
from rich.prompt import Prompt
from rich import print
from mcp_agent.progress_display import progress_display
from mcp_agent.workflows.llm.model_factory import ModelFactory

import readline  # noqa: F401

from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM  # noqa: F401


class AgentType(Enum):
    """Enumeration of supported agent types."""
    BASIC = "agent"
    ORCHESTRATOR = "orchestrator"
    PARALLEL = "parallel"


T = TypeVar('T')  # For the wrapper classes


class BaseAgentWrapper(Generic[T]):
    """
    Base wrapper class for all agent types.
    
    Provides a consistent interface for different types of agents (basic, orchestrator, parallel)
    by implementing the common protocol expected by the agent application.
    
    Args:
        agent: The underlying agent implementation
    """
    def __init__(self, agent: T):
        self._llm = agent
        self.name = agent.name

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MCPAgentDecorator(ContextDependent):
    """
    A decorator-based interface for MCP Agent applications.
    Provides a simplified way to create and manage agents using decorators.
    """

    def __init__(self, name: str, config_path: Optional[str] = None):
        """
        Initialize the decorator interface.

        Args:
            name: Name of the application
            config_path: Optional path to config file
        """
        # Initialize ContextDependent
        super().__init__()

        # Setup command line argument parsing
        parser = argparse.ArgumentParser(description="MCP Agent Application")
        parser.add_argument(
            "--model",
            help="Override the default model for all agents. Precedence is default < config_file < command line < constructor",
        )
        self.args = parser.parse_args()

        self.name = name
        self.config_path = config_path
        self._load_config()
        self.app = MCPApp(
            name=name,
            settings=Settings(**self.config) if hasattr(self, "config") else None,
        )
        self.agents: Dict[str, Dict[str, Any]] = {}

    @property
    def context(self):
        """Access the application context"""
        return self.app.context

    def _load_config(self) -> None:
        """Load configuration from YAML file, properly handling without dotenv processing"""
        if self.config_path:
            with open(self.config_path) as f:
                self.config = yaml.safe_load(f)

    def _get_model_factory(self, model: Optional[str] = None) -> Any:
        """
        Get model factory using specified or default model.
        
        Args:
            model: Optional model specification string
            
        Returns:
            ModelFactory instance for the specified or default model
        """
        model_spec = model or self.args.model
        if not model_spec:
            model_spec = self.context.config.default_model
        return ModelFactory.create_factory(model_spec)

    def agent(
        self,
        name: str,
        instruction: str,
        servers: List[str] = [],
        model: Optional[str] = None,
    ) -> Callable:
        """
        Decorator to create and register an agent.

        Args:
            name: Name of the agent
            instruction: Base instruction for the agent
            servers: List of server names the agent should connect to
            model: Model specification string (default: None, uses app default)
        """

        def decorator(func: Callable) -> Callable:
            # Store the agent configuration for later instantiation
            self.agents[name] = {
                "instruction": instruction,
                "servers": servers,
                "model": model,
                "type": AgentType.BASIC.value,
            }

            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def orchestrator(
        self,
        name: str,
        instruction: str,
        agents: List[str],
        model: Optional[str] = None,
    ) -> Callable:
        """
        Decorator to create and register an orchestrator.

        Args:
            name: Name of the orchestrator
            instruction: Base instruction for the orchestrator
            agents: List of agent names this orchestrator can use
            model: Model specification string (required for orchestrator)
        """

        def decorator(func: Callable) -> Callable:
            # Store the orchestrator configuration like any other agent
            self.agents[name] = {
                "instruction": instruction,
                "child_agents": agents,
                "model": model,
                "type": AgentType.ORCHESTRATOR.value,
            }

            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def parallel(
        self,
        name: str,
        fan_in: str,
        fan_out: List[str],
        instruction: str = "",
        model: Optional[str] = None,
    ) -> Callable:
        """
        Decorator to create and register a parallel executing agent.

        Args:
            name: Name of the parallel executing agent
            fan_in: Name of collecting agent
            fan_out: List of parallel execution agents
            instruction: Optional instruction for the parallel agent
            model: Model specification string
        """

        def decorator(func: Callable) -> Callable:
            # Store the parallel configuration
            self.agents[name] = {
                "instruction": instruction,
                "fan_out": fan_out,
                "fan_in": fan_in,
                "model": model,
                "type": AgentType.PARALLEL.value,
            }

            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def _create_basic_agents(self, agent_app: MCPApp) -> Dict[str, Agent]:
        """
        Create and initialize basic agents.
        
        Args:
            agent_app: The main application instance
            
        Returns:
            Dictionary of initialized basic agents
        """
        active_agents = {}
        for name, config in self.agents.items():
            if config["type"] == AgentType.BASIC.value:
                agent = Agent(
                    name=name,
                    instruction=config["instruction"],
                    server_names=config["servers"],
                    context=agent_app.context,
                )
                active_agents[name] = agent
        return active_agents

    def _create_orchestrators(
        self, agent_app: MCPApp, active_agents: Dict[str, Any]
    ) -> Dict[str, BaseAgentWrapper]:
        """
        Create orchestrator agents.
        
        Args:
            agent_app: The main application instance
            active_agents: Dictionary of already created agents
            
        Returns:
            Dictionary of initialized orchestrator agents
        """
        orchestrators = {}
        for name, config in self.agents.items():
            if config["type"] == AgentType.ORCHESTRATOR.value:
                # Get the child agents
                child_agents = [
                    active_agents[agent_name] for agent_name in config["child_agents"]
                ]

                # Create orchestrator with its agents and model
                llm_factory = self._get_model_factory(config["model"])
                print(f"ORCHESTRATOR MODEL {config['model']}")

                orchestrator = Orchestrator(
                    name=name,
                    instruction=config["instruction"],
                    available_agents=child_agents,
                    context=agent_app.context,
                    llm_factory=llm_factory,
                    plan_type="full",
                )

                orchestrators[name] = BaseAgentWrapper(orchestrator)
        return orchestrators

    def _create_parallel_agents(
        self, agent_app: MCPApp, active_agents: Dict[str, Any]
    ) -> Dict[str, BaseAgentWrapper]:
        """
        Create parallel execution agents.
        
        Args:
            agent_app: The main application instance
            active_agents: Dictionary of already created agents
            
        Returns:
            Dictionary of initialized parallel agents
        """
        parallel_agents = {}
        for name, config in self.agents.items():
            if config["type"] == AgentType.PARALLEL.value:
                # Get the fan-out agents
                fan_out_agents = [
                    active_agents[agent_name] for agent_name in config["fan_out"]
                ]

                # Get the fan-in agent
                fan_in_agent = active_agents[config["fan_in"]]

                # Create the parallel workflow
                llm_factory = self._get_model_factory(config["model"])
                parallel = ParallelLLM(
                    name=name,
                    instruction=config["instruction"],
                    fan_out_agents=fan_out_agents,
                    fan_in_agent=fan_in_agent,
                    context=agent_app.context,
                    llm_factory=llm_factory,
                )

                parallel_agents[name] = BaseAgentWrapper(parallel)
        return parallel_agents

    @asynccontextmanager
    async def run(self):
        """
        Context manager for running the application.
        Handles setup and teardown of the app and agents.
        
        Yields:
            AgentAppWrapper instance with all initialized agents
        """
        async with self.app.run() as agent_app:
            # Create all types of agents
            active_agents = self._create_basic_agents(agent_app)
            
            # Create orchestrators and parallel agents
            orchestrators = self._create_orchestrators(agent_app, active_agents)
            parallel_agents = self._create_parallel_agents(agent_app, active_agents)
            
            # Merge all agents into active_agents
            active_agents.update(orchestrators)
            active_agents.update(parallel_agents)

            # Start all basic agents with LLM
            agent_contexts = []
            for name, agent in active_agents.items():
                if isinstance(agent, Agent):  # Basic agents need LLM setup
                    ctx = await agent.__aenter__()
                    agent_contexts.append((agent, ctx))
                    llm_factory = self._get_model_factory(self.agents[name]["model"])
                    agent._llm = await agent.attach_llm(llm_factory)

            # Create wrapper with all agents
            wrapper = AgentAppWrapper(agent_app, active_agents)
            try:
                yield wrapper
            finally:
                for agent, _ in agent_contexts:
                    await agent.__aexit__(None, None, None)


class AgentAppWrapper:
    """
    Wrapper class providing a simplified interface to the agent application.
    Manages communication with agents and provides interactive prompting.
    """

    def __init__(self, app: MCPApp, agents: Dict[str, Any]):
        self.app = app
        self.agents = agents
        self._default_agent = next(iter(agents)) if agents else None

    async def send(self, agent_name: str, message: str) -> Any:
        """
        Send a message to a specific agent and get the response.
        
        Args:
            agent_name: Name of the target agent
            message: Message to send
            
        Returns:
            Agent's response
            
        Raises:
            ValueError: If agent not found
            RuntimeError: If agent has no LLM attached
        """
        if agent_name not in self.agents:
            raise ValueError(f"Agent {agent_name} not found")

        agent = self.agents[agent_name]
        if not hasattr(agent, "_llm") or agent._llm is None:
            raise RuntimeError(f"Agent {agent_name} has no LLM attached")
        return await agent._llm.generate_str(message)

    async def __call__(self, message: str, agent_name: Optional[str] = None) -> Any:
        """
        Send a message using direct call syntax.
        
        Args:
            message: Message to send
            agent_name: Optional target agent name (uses default if not specified)
            
        Returns:
            Agent's response
        """
        target_agent = agent_name or self._default_agent
        if not target_agent:
            raise ValueError("No agents available")
        return await self.send(target_agent, message)

    async def prompt(self, agent_name: Optional[str] = None, default: str = "") -> None:
        """
        Interactive prompt for sending messages.
        
        Args:
            agent_name: Optional target agent name (uses default if not specified)
            default: Default message to use when user presses enter
        """
        target_agent = agent_name or self._default_agent
        if not target_agent:
            raise ValueError("No agents available")

        while True:
            with progress_display.paused():
                if default == "STOP":
                    print("Press <ENTER> to finish")
                elif default != "":
                    print("Enter a prompt, or [red]STOP[/red] to finish")
                    print(
                        f"Press <ENTER> to use the default prompt:\n[cyan]{default}[/cyan]"
                    )
                else:
                    print("Enter a prompt, or enter [red]STOP[/red] to finish")

                prompt_text = f"[blue]{target_agent}[/blue] >"
                user_input = Prompt.ask(
                    prompt=prompt_text, default=default, show_default=False
                )

                if user_input.upper() == "STOP":
                    return

            await self.send(target_agent, user_input)