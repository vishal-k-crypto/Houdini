from typing import Dict, List, Tuple
from .grounding import ACI
from .worker import Worker
from ..utils.gemini_client import GeminiCLI

class AgentS:
    """
    The main Agent-S class (AgentS3).
    Wraps the Worker and Grounding components.
    """
    def __init__(self, cli: GeminiCLI, platform: str = "darwin", max_trajectory: int = 8):
        self.cli = cli
        self.platform = platform
        
        # Initialize components
        self.aci = ACI(grounding_model=cli, platform_name=platform)
        self.worker = Worker(
            cli=cli,
            aci=self.aci,
            platform=platform,
            max_trajectory=max_trajectory,
            enable_reflection=True
        )

    def reset(self):
        self.worker.reset()

    def predict(self, instruction: str, obs: Dict) -> Tuple[Dict, List[str]]:
        """
        Predict the next action.
        """
        info = self.worker.step(instruction, obs)
        # Agent-S returns (info, actions_list)
        # Our worker executes internally, so we return the action string for logging
        trajectory_step = self.worker.trajectory[-1]
        action_str = trajectory_step['action']
        
        return info, [action_str]
