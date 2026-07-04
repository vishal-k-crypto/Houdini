"""Set-of-Marks (SoM) rendering for browser screenshots.

Draws numbered markers on interactive elements so a vision model can refer to
elements by ID instead of brittle CSS selectors.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


@dataclass
class SOMRenderResult:
    """Result of rendering Set-of-Marks on a screenshot."""

    image: Image.Image
    marks: List[Dict[str, Any]]
    id_to_element: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    @property
    def base64_png(self) -> str:
        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


class SetOfMarksRenderer:
    """Render numbered markers on interactive browser elements."""

    def __init__(
        self,
        marker_radius: int = 12,
        marker_color: Tuple[int, int, int, int] = (255, 0, 0, 200),
        text_color: Tuple[int, int, int] = (255, 255, 255),
    ):
        self.marker_radius = marker_radius
        self.marker_color = marker_color
        self.text_color = text_color

    def render(
        self,
        screenshot: Image.Image,
        elements: List[Dict[str, Any]],
    ) -> SOMRenderResult:
        """Draw numbered markers and return the annotated image + mappings."""
        img = screenshot.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        marks: List[Dict[str, Any]] = []
        id_to_element: Dict[int, Dict[str, Any]] = {}

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
        except Exception:
            font = ImageFont.load_default()

        for idx, element in enumerate(elements, start=1):
            bbox = element.get("bbox") or {}
            x = int(bbox.get("x", 0))
            y = int(bbox.get("y", 0))
            width = int(bbox.get("width", 0))
            height = int(bbox.get("height", 0))
            if width <= 0 or height <= 0:
                continue

            center_x = x + width // 2
            center_y = y + height // 2
            r = self.marker_radius
            draw.ellipse(
                [center_x - r, center_y - r, center_x + r, center_y + r],
                fill=self.marker_color,
            )
            text = str(idx)
            bbox_text = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]
            draw.text(
                (center_x - tw / 2, center_y - th / 2),
                text,
                font=font,
                fill=self.text_color,
            )

            mark = {
                "som_id": idx,
                "bbox": bbox,
                "text": element.get("text", ""),
                "tag": element.get("tag", ""),
            }
            marks.append(mark)
            id_to_element[idx] = element

        annotated = Image.alpha_composite(img, overlay)
        return SOMRenderResult(image=annotated.convert("RGB"), marks=marks, id_to_element=id_to_element)
