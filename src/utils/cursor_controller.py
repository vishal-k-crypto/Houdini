"""
Human-Like Cursor Controller
Implements natural mouse movements using bezier curves, Fitts's Law, and micro-variations.

Based on research:
- Fitts's Law for movement time calculation
- Bezier curves for natural arcing paths
- Random micro-jitter to mimic human imprecision
- Speed profiles (slow start, fast middle, slow end)
"""

import time
import random
import math
import subprocess
from typing import Tuple, List, Optional
from dataclasses import dataclass
import pyautogui
from ..utils.logging import logger


def get_macos_scale_factor() -> float:
    """
    Detect the screen scale factor for macOS Retina displays.
    
    AI models typically return coordinates in pixels (Retina resolution),
    but PyAutoGUI operates in points. This function returns the scale
    factor to convert between them.
    
    Returns:
        2.0 for Retina displays, 1.0 for standard displays
    """
    try:
        # Check for Retina scaling on macOS
        cmd = "system_profiler SPDisplaysDataType | grep -i 'Retina'"
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
        if "Retina" in result:
            return 2.0
    except Exception:
        pass
    return 1.0


# Cache the scale factor at module load time
_MACOS_SCALE_FACTOR: Optional[float] = None


def get_scale_factor() -> float:
    """Get cached macOS scale factor."""
    global _MACOS_SCALE_FACTOR
    if _MACOS_SCALE_FACTOR is None:
        _MACOS_SCALE_FACTOR = get_macos_scale_factor()
        logger.debug(f"Detected macOS scale factor: {_MACOS_SCALE_FACTOR}")
    return _MACOS_SCALE_FACTOR

try:
    import numpy as np
    from scipy import interpolate
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("numpy/scipy not available. Using fallback linear movement.")


@dataclass
class MovementConfig:
    """Configuration for cursor movement behavior."""
    # Fitts's Law parameters
    fitts_a: float = 0.1  # Empirical constant (seconds)
    fitts_b: float = 0.2  # Empirical constant (seconds/bit)
    
    # Movement characteristics
    overshoot_probability: float = 0.15  # Chance of overshooting target
    overshoot_distance: Tuple[int, int] = (5, 15)  # Overshoot range (pixels)
    
    # Jitter/noise
    path_jitter: float = 2.0  # Random deviation during movement (pixels)
    final_jitter: float = 1.0  # Final position randomization (pixels)
    
    # Speed profile
    min_duration: float = 0.1  # Minimum movement duration (seconds)
    max_duration: float = 1.5  # Maximum movement duration (seconds)
    
    # Bezier control points
    bezier_complexity: int = 2  # Number of control points (1-3)


class BezierCurve:
    """Generate smooth bezier curves for natural cursor paths."""
    
    @staticmethod
    def calculate_bezier_points(
        start: Tuple[float, float],
        end: Tuple[float, float],
        control_points: List[Tuple[float, float]],
        num_samples: int = 100
    ) -> List[Tuple[int, int]]:
        """
        Calculate points along a bezier curve.
        
        Args:
            start: Starting position (x, y)
            end: Ending position (x, y)
            control_points: List of control points for curve shaping
            num_samples: Number of points to generate
            
        Returns:
            List of (x, y) coordinates along the curve
        """
        if not NUMPY_AVAILABLE:
            # Fallback: linear interpolation
            return [
                (
                    int(start[0] + (end[0] - start[0]) * t),
                    int(start[1] + (end[1] - start[1]) * t)
                )
                for t in np.linspace(0, 1, num_samples)
            ]
        
        # Construct bezier curve
        all_points = [start] + control_points + [end]
        n = len(all_points) - 1
        
        points = []
        for t in np.linspace(0, 1, num_samples):
            # Bezier formula
            x = sum(
                math.comb(n, i) * (1 - t)**(n - i) * t**i * all_points[i][0]
                for i in range(n + 1)
            )
            y = sum(
                math.comb(n, i) * (1 - t)**(n - i) * t**i * all_points[i][1]
                for i in range(n + 1)
            )
            points.append((int(x), int(y)))
        
        return points
    
    @staticmethod
    def generate_control_points(
        start: Tuple[float, float],
        end: Tuple[float, float],
        num_points: int = 1
    ) -> List[Tuple[float, float]]:
        """
        Generate random control points between start and end for natural curves.
        
        Args:
            start: Starting position
            end: Ending position
            num_points: Number of control points to generate
            
        Returns:
            List of control point coordinates
        """
        control_points = []
        
        for i in range(num_points):
            # Progress along the path
            t = (i + 1) / (num_points + 1)
            
            # Interpolate base position
            base_x = start[0] + (end[0] - start[0]) * t
            base_y = start[1] + (end[1] - start[1]) * t
            
            # Add perpendicular offset for arc
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            distance = math.sqrt(dx**2 + dy**2)
            
            # Offset proportional to distance
            max_offset = min(distance * 0.2, 100)
            offset = random.uniform(-max_offset, max_offset)
            
            # Perpendicular vector
            if distance > 0:
                offset_x = -dy / distance * offset
                offset_y = dx / distance * offset
            else:
                offset_x = 0
                offset_y = 0
            
            control_points.append((base_x + offset_x, base_y + offset_y))
        
        return control_points


class FittsLawCalculator:
    """Calculate movement time based on Fitts's Law."""
    
    @staticmethod
    def calculate_movement_time(
        distance: float,
        target_width: float,
        config: MovementConfig
    ) -> float:
        """
        Calculate movement time using Fitts's Law.
        
        Fitts's Law: MT = a + b * log2(D/W + 1)
        where:
            MT = Movement Time
            D = Distance to target
            W = Width of target
            a, b = empirical constants
            
        Args:
            distance: Distance to move (pixels)
            target_width: Width of target element (pixels)
            config: Movement configuration
            
        Returns:
            Estimated movement time (seconds)
        """
        if distance < 1:
            return config.min_duration
        
        if target_width < 1:
            target_width = 10  # Default small target
        
        # Fitts's Law calculation
        index_of_difficulty = math.log2(distance / target_width + 1)
        movement_time = config.fitts_a + config.fitts_b * index_of_difficulty
        
        # Add random variation (humans aren't perfectly consistent)
        variation = random.uniform(0.9, 1.1)
        movement_time *= variation
        
        # Clamp to reasonable bounds
        movement_time = max(config.min_duration, min(config.max_duration, movement_time))
        
        return movement_time


class HumanCursor:
    """
    Advanced cursor controller with human-like movement.
    
    Features:
    - Bezier curve paths for natural arcing
    - Fitts's Law for realistic timing
    - Random overshoots and corrections
    - Micro-jitter during movement
    - Variable speed profiles
    """
    
    def __init__(self, config: Optional[MovementConfig] = None):
        self.config = config or MovementConfig()
        pyautogui.PAUSE = 0  # We handle timing ourselves
        pyautogui.FAILSAFE = True
    
    def get_current_position(self) -> Tuple[int, int]:
        """Get current cursor position."""
        return pyautogui.position()
    
    def move_to(
        self,
        x: int,
        y: int,
        target_size: Tuple[int, int] = (10, 10),
        human_like: bool = True
    ):
        """
        Move cursor to target position with human-like movement.
        
        Args:
            x, y: Target coordinates (in AI/pixel coordinates)
            target_size: (width, height) of target element for Fitts's Law
            human_like: Whether to use natural movement (vs instant)
            
        Note:
            On macOS Retina displays, coordinates are automatically scaled
            from pixels to points to fix coordinate mismatch issues.
        """
        # Apply macOS Retina scaling (AI gives pixels, PyAutoGUI needs points)
        scale = get_scale_factor()
        if scale != 1.0:
            x = int(x / scale)
            y = int(y / scale)
            target_size = (int(target_size[0] / scale), int(target_size[1] / scale))
            logger.debug(f"Scaled coordinates by {scale}: ({x}, {y})")
        
        if not human_like:
            pyautogui.moveTo(x, y, duration=0)
            return
        
        start_x, start_y = self.get_current_position()
        
        # Calculate distance
        distance = math.sqrt((x - start_x)**2 + (y - start_y)**2)
        
        if distance < 3:
            # Too close, just move instantly
            pyautogui.moveTo(x, y, duration=0)
            return
        
        # Determine if we should overshoot
        should_overshoot = random.random() < self.config.overshoot_probability
        
        # Calculate movement time using Fitts's Law
        target_width = max(target_size)
        duration = FittsLawCalculator.calculate_movement_time(
            distance, target_width, self.config
        )
        
        logger.debug(f"Moving {distance:.0f}px in {duration:.2f}s (Fitts's Law)")
        
        # Generate bezier path
        if NUMPY_AVAILABLE and self.config.bezier_complexity > 0:
            control_points = BezierCurve.generate_control_points(
                (start_x, start_y),
                (x, y),
                num_points=self.config.bezier_complexity
            )
            
            # If overshooting, adjust final point
            final_x, final_y = x, y
            if should_overshoot:
                overshoot = random.randint(*self.config.overshoot_distance)
                angle = math.atan2(y - start_y, x - start_x)
                final_x += int(overshoot * math.cos(angle))
                final_y += int(overshoot * math.sin(angle))
            
            # Generate smooth path
            path = BezierCurve.calculate_bezier_points(
                (start_x, start_y),
                (final_x, final_y),
                control_points,
                num_samples=max(int(distance / 3), 20)
            )
        else:
            # Fallback: linear interpolation with jitter
            steps = max(int(distance / 5), 10)
            path = [
                (
                    int(start_x + (x - start_x) * i / steps + random.uniform(-self.config.path_jitter, self.config.path_jitter)),
                    int(start_y + (y - start_y) * i / steps + random.uniform(-self.config.path_jitter, self.config.path_jitter))
                )
                for i in range(steps + 1)
            ]
        
        # Execute movement along path with easing
        start_time = time.time()
        total_points = len(path)
        
        for i, (px, py) in enumerate(path):
            # Easing function (slow start, fast middle, slow end)
            progress = i / total_points
            eased_progress = self._ease_in_out_cubic(progress)
            
            # Add micro jitter
            jitter_x = random.uniform(-self.config.path_jitter, self.config.path_jitter)
            jitter_y = random.uniform(-self.config.path_jitter, self.config.path_jitter)
            
            pyautogui.moveTo(px + jitter_x, py + jitter_y, duration=0)
            
            # Sleep for realistic timing
            elapsed = time.time() - start_time
            expected_time = duration * eased_progress
            sleep_time = max(0, expected_time - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        # Overshoot correction
        if should_overshoot:
            time.sleep(random.uniform(0.05, 0.15))
            # Correct back to target
            pyautogui.moveTo(
                x + random.uniform(-self.config.final_jitter, self.config.final_jitter),
                y + random.uniform(-self.config.final_jitter, self.config.final_jitter),
                duration=random.uniform(0.1, 0.2)
            )
        else:
            # Final position with slight jitter
            pyautogui.moveTo(
                x + random.uniform(-self.config.final_jitter, self.config.final_jitter),
                y + random.uniform(-self.config.final_jitter, self.config.final_jitter),
                duration=0
            )
    
    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = 'left', clicks: int = 1):
        """
        Click at position with human-like timing.
        
        Args:
            x, y: Position to click (None = current position)
            button: 'left', 'right', or 'middle'
            clicks: Number of clicks (1 = single, 2 = double)
        """
        if x is not None and y is not None:
            current_x, current_y = self.get_current_position()
            if (current_x, current_y) != (x, y):
                self.move_to(x, y)
        
        # Human-like pause before clicking
        time.sleep(random.uniform(0.05, 0.15))
        
        # Click with slight randomness in timing
        for i in range(clicks):
            pyautogui.click(button=button)
            if i < clicks - 1:
                time.sleep(random.uniform(0.1, 0.2))
        
        logger.info(f"Clicked at ({x}, {y}) with {button} button")
    
    def click_element(self, element):
        """
        Click a UI element (from accessibility_api or accessibility_reader).
        
        Args:
            element: UIElement or AXElement with center property
        """
        if not hasattr(element, 'center'):
            raise ValueError("Element must have 'center' property")
        
        center = element.center
        if not center:
            raise ValueError(f"Element {element} has no position information")
        
        x, y = center
        
        # Determine target size for Fitts's Law
        if hasattr(element, 'size') and element.size:
            target_size = element.size
        elif hasattr(element, 'width') and hasattr(element, 'height'):
            target_size = (element.width, element.height)
        else:
            target_size = (10, 10)  # Default small target
        
        self.move_to(x, y, target_size=target_size)
        self.click()
        
        logger.info(f"Clicked element: {element}")
    
    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_variance: float = 0.2
    ):
        """
        Drag from start to end with human-like movement.
        
        Args:
            start_x, start_y: Starting position
            end_x, end_y: Ending position
            duration_variance: Random variance in duration (0.0 - 1.0)
        """
        self.move_to(start_x, start_y)
        time.sleep(random.uniform(0.05, 0.15))
        
        # Calculate base duration
        distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        base_duration = distance / 500  # ~500 pixels per second
        duration = base_duration * random.uniform(1 - duration_variance, 1 + duration_variance)
        
        pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration, button='left')
        
        logger.info(f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})")
    
    @staticmethod
    def _ease_in_out_cubic(t: float) -> float:
        """
        Cubic easing function for smooth acceleration/deceleration.
        
        Args:
            t: Progress from 0.0 to 1.0
            
        Returns:
            Eased value from 0.0 to 1.0
        """
        if t < 0.5:
            return 4 * t * t * t
        else:
            p = 2 * t - 2
            return 1 + p * p * p / 2


# Convenience functions
_global_cursor = None

def get_cursor() -> HumanCursor:
    """Get global cursor instance."""
    global _global_cursor
    if _global_cursor is None:
        _global_cursor = HumanCursor()
    return _global_cursor


def human_click(x: int, y: int, button: str = 'left'):
    """Quick function for human-like clicking."""
    cursor = get_cursor()
    cursor.move_to(x, y)
    cursor.click()


def human_move(x: int, y: int, target_size: Tuple[int, int] = (10, 10)):
    """Quick function for human-like movement."""
    cursor = get_cursor()
    cursor.move_to(x, y, target_size=target_size)
