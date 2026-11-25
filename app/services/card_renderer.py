import argparse
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal
from unicodedata import normalize

from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from app.schemas.card_news import CARD_COUNT, CardDraft, CardNewsContent

CARD_SIZE = (1080, 1350)
FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "PretendardVariable.ttf"
HEADER_COLOR = "#14372F"
BACKGROUND_COLOR = "#F4F7EF"
TEXT_COLOR = "#182D27"
ACCENT_COLOR = "#D4F39C"


@dataclass(frozen=True)
class TextArea:
    name: Literal["title", "body"]
    x: int
    y: int
    width: int
    height: int
    line_spacing: int


TITLE_AREA = TextArea("title", x=88, y=213, width=904, height=300, line_spacing=14)
BODY_AREA = TextArea("body", x=88, y=660, width=904, height=485, line_spacing=21)


class TextOverflowError(ValueError):
    def __init__(self, card_id: str, area: Literal["title", "body"]) -> None:
        self.card_id = card_id
        self.area = area
        super().__init__(f"카드 {card_id}의 {area} 영역에 텍스트가 들어가지 않습니다.")


@dataclass(frozen=True)
class RenderedCard:
    card_id: str
    order: int
    jpeg: bytes


def _load_font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(FONT_PATH, size=size)
    font.set_variation_by_axes([weight])
    return font


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int
) -> str:
    def fits(line: str) -> bool:
        left, _, right, _ = draw.textbbox((0, 0), line, font=font)
        return right - min(left, 0) <= width

    lines = []
    for paragraph in normalize("NFC", text).splitlines():
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if fits(candidate):
                line = candidate
                continue

            if line:
                lines.append(line)
            line = word
            if fits(word):
                continue

            # Keep long words and Korean text without spaces inside the area.
            line = ""
            for character in word:
                if line and not fits(line + character):
                    lines.append(line)
                    line = ""
                line += character
        lines.append(line)
    return "\n".join(lines)


def _draw_text_area(
    draw: ImageDraw.ImageDraw,
    card_id: str,
    text: str,
    area: TextArea,
    font: ImageFont.FreeTypeFont,
    color: str,
) -> None:
    wrapped = _wrap_text(draw, text, font, area.width)
    left, top, right, bottom = draw.multiline_textbbox(
        (0, 0), wrapped, font=font, spacing=area.line_spacing
    )
    if right - left > area.width or bottom - top > area.height:
        raise TextOverflowError(card_id, area.name)

    draw.multiline_text(
        (area.x - left, area.y - top),
        wrapped,
        font=font,
        fill=color,
        spacing=area.line_spacing,
    )


def _render_card(
    card: CardDraft,
    title_font: ImageFont.FreeTypeFont,
    body_font: ImageFont.FreeTypeFont,
    label_font: ImageFont.FreeTypeFont,
) -> RenderedCard:
    with Image.new("RGB", CARD_SIZE, BACKGROUND_COLOR) as image:
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, CARD_SIZE[0] - 1, 575), fill=HEADER_COLOR)
        draw.text((88, 91), "경제 브리핑", font=label_font, fill=ACCENT_COLOR, anchor="lt")
        _draw_text_area(draw, card.card_id, card.title, TITLE_AREA, title_font, BACKGROUND_COLOR)
        _draw_text_area(draw, card.card_id, card.body, BODY_AREA, body_font, TEXT_COLOR)
        draw.line((88, 1206, 992, 1206), fill="#A8B9A9", width=2)
        draw.text((88, 1249), "ReelCrew", font=label_font, fill=TEXT_COLOR, anchor="lt")
        draw.text(
            (992, 1249),
            f"{card.order} / {CARD_COUNT}",
            font=label_font,
            fill=TEXT_COLOR,
            anchor="rt",
        )

        with BytesIO() as output:
            image.save(output, format="JPEG", quality=92)
            return RenderedCard(card.card_id, card.order, output.getvalue())


def render_card_news(content: CardNewsContent) -> list[RenderedCard]:
    title_font = _load_font(size=89, weight=750)
    body_font = _load_font(size=54, weight=450)
    label_font = _load_font(size=33, weight=650)
    return [_render_card(card, title_font, body_font, label_font) for card in content.draft.cards]


def main() -> None:
    parser = argparse.ArgumentParser(description="검증된 카드뉴스 원고를 JPEG로 렌더링합니다.")
    parser.add_argument("input", type=Path, help="출처와 원고가 담긴 JSON 파일")
    args = parser.parse_args()

    try:
        content = CardNewsContent.model_validate_json(args.input.read_bytes())
        cards = render_card_news(content)
        directory = Path(mkdtemp(prefix="reelcrew-cards-"))
        for card in cards:
            (directory / f"card-{card.order:02}.jpg").write_bytes(card.jpeg)
    except (OSError, ValidationError, TextOverflowError) as error:
        parser.exit(1, f"{error}\n")
    print(directory)


if __name__ == "__main__":
    main()
