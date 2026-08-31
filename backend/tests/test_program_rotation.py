from concurrent.futures import ThreadPoolExecutor
import asyncio
from unittest.mock import AsyncMock, Mock

from backend.app.services.program_rotation_service import ProgramRotationService
from backend.app.automations.utel_inconcert.runner import UtelInconcertRunner
from backend.app.config.settings import Settings
from backend.app.schemas.bot import UtelQaConfig, UtelLead


def options(*names):
    return [{"text": name, "value": name} for name in names]


def test_persistent_rotation_and_changed_availability(tmp_path):
    path = tmp_path / "rotation.db"
    scope = ["Mexico", "Maestria", "En linea", "footer", "dry_run"]
    def choose(names):
        return ProgramRotationService(path).choose(scope, options(*names))["text"]
    assert [choose("ABC") for _ in range(3)] == list("ABC")
    assert choose("ABCD") == "D"
    assert choose("BC") == "B"
    assert choose("ABC") == "A"


def test_isolated_scopes_and_single_candidate(tmp_path):
    service = ProgramRotationService(tmp_path / "rotation.db")
    scope = ["Mexico", "Doctorado", "En linea", "tarjeta", "dry_run"]
    assert service.choose(scope, options("A", "B"))["text"] == "A"
    for index, replacement in enumerate(["Peru", "Maestria", "Hibrida", "footer", "real"]):
        other = scope.copy()
        other[index] = replacement
        assert service.choose(other, options("A", "B"))["text"] == "A"
    assert service.choose(scope, options("A", "B"))["text"] == "B"
    assert service.choose(scope, options("A"))["text"] == "A"


def test_parallel_reservations_do_not_repeat(tmp_path):
    service = ProgramRotationService(tmp_path / "rotation.db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        selected = list(pool.map(lambda _: service.choose(["scope"], options("A", "B", "C", "D"))["text"], range(4)))
    assert len(set(selected)) == 4


def test_cards_rotate_and_click_explore(tmp_path):
    cards = Mock()
    cards.first.wait_for = AsyncMock()
    cards.count = AsyncMock(return_value=2)
    targets = []
    card_list = []
    for label in ("Doctorado A", "Doctorado B"):
        card = Mock()
        text = Mock(count=AsyncMock(return_value=1), inner_text=AsyncMock(return_value=label))
        target = Mock(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True),
                      scroll_into_view_if_needed=AsyncMock(), click=AsyncMock())
        card.locator.return_value = Mock(first=text, count=AsyncMock(return_value=0))
        card.get_by_text.return_value.first = target
        targets.append(target)
        card_list.append(card)
    cards.nth.side_effect = lambda index: card_list[index]
    page = Mock(url="https://utel.test/doctorados")
    page.locator.return_value = cards
    config = UtelQaConfig(country="Mexico", level="Doctorado", modality="En linea", form_type="tarjeta",
                          utel_url=page.url, dry_run=True, lead=UtelLead())
    for expected in ("Doctorado A", "Doctorado B"):
        runner = UtelInconcertRunner(Settings(database_path=tmp_path / "rotation.db"))
        runner._rotation_config = config
        asyncio.run(runner._click_first_program_card(page))
        assert runner.selected_program_name == expected
    for target in targets:
        target.click.assert_awaited_once()
