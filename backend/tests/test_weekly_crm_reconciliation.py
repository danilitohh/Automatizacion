"""Regresiones de los leads recuperados sin reenvíos del lote Weekly Forms."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.app.api.routes import _is_support_rejection, _is_post_submit_crm_retry_candidate
from backend.app.config.settings import Settings
from backend.app.modules.bot_leads_deploy.runner import UtelQaError, UnconfirmedSubmission, UtelInconcertRunner
from backend.app.modules.weekly_auto.weekly_forms import WeeklyFormsRunner, WeeklyFormsCaseConfig


@pytest.mark.parametrize('found', [True, False])
def test_http_500_verifies_same_identity_without_becoming_a_phone_retry(tmp_path, found):
    """El flujo real concilia un POST incierto incluso si el toast dice soporte."""
    async def scenario():
        runner = WeeklyFormsRunner(Settings(storage_dir=tmp_path, database_path=tmp_path / 'qa.db'))
        page = Mock(url='https://utel.test/landing')
        context = Mock(new_page=AsyncMock(return_value=page))

        @asynccontextmanager
        async def browser_context(_config):
            yield context

        runner._browser_context = browser_context
        runner._safe_screenshot = AsyncMock(return_value=None)
        for method in ('_open_utel', '_navigate_utel', '_find_utel_form', '_fill_utel_form',
                       '_open_inconcert', '_login_inconcert', '_open_contacts'):
            setattr(runner, method, AsyncMock(return_value=None))

        async def submit(*_args):
            runner._submission_attempted = True
            response = SimpleNamespace(status=500, text=AsyncMock(return_value='Internal server error'))
            await runner._classify_utel_api_response(response, 'Error al enviar. Contacta a soporte')

        async def find_balancer(_page, email, name):
            assert (email, name) == ('original@example.test', 'Persona QA')
            if not found:
                raise UtelQaError('lead_balancer_search', 'Balancer no disponible')
            runner.lead_url = 'https://lead-balancer.scalahed.com/leads/detail/123'

        runner._submit_utel_form = AsyncMock(side_effect=submit)
        runner._search_lead = AsyncMock(side_effect=UtelQaError('inconcert_search', 'InConcert no disponible'))
        runner._search_lead_balancer = AsyncMock(side_effect=find_balancer)
        config = WeeklyFormsCaseConfig(
            country='Mexico', utel_url='https://utel.test/landing', inconcert_url='https://crm.test',
            level='Licenciatura', modality='En linea', workflow_mode='form_validation',
            parallel_crm_search=True, lead_search_destination='both', dry_run=False,
            lead={'name':'Persona QA', 'email':'original@example.test', 'phone':'5551234567'},
        )
        result = await runner.run(config)
        result['stages'] = [stage.model_dump() for stage in result['stages']]
        runner._submit_utel_form.assert_awaited_once()
        runner._search_lead.assert_awaited_once_with(page, config.lead.email, config.lead.name)
        runner._search_lead_balancer.assert_awaited_once_with(page, config.lead.email, config.lead.name)
        assert result['utel_submission'] == ('success' if found else 'pending')
        assert not _is_support_rejection(result)
        assert _is_post_submit_crm_retry_candidate(result) is (not found)
        assert result['lead_phone'] == '5551234567'
        if not found:
            assert _is_post_submit_crm_retry_candidate(result)
            assert 'InConcert no disponible' in result['error']
            assert 'Balancer no disponible' in result['error']
    asyncio.run(scenario())


def test_dual_crm_does_not_repeat_a_completed_fallback(tmp_path):
    """Los dos diagnósticos se conservan sin programar una tercera búsqueda."""
    runner = WeeklyFormsRunner(Settings(storage_dir=tmp_path))
    result = {'status':'FAIL', 'utel_submission_attempted':True, 'stages':[
        {'stage':'inconcert_search', 'status':'FAIL', 'message':'Filtro no disponible'},
        {'stage':'lead_balancer_search', 'status':'FAIL', 'message':'No encontrado'},
    ]}
    config = WeeklyFormsCaseConfig(country='Mexico', utel_url='https://utel.test/', level='Licenciatura',
                                   modality='En linea', lead={})
    assert runner._secondary_verification_config(config, result) is None


def test_dual_merge_keeps_both_crm_diagnostics():
    """El segundo resultado no reemplaza el error del primero en la respuesta API."""
    config = WeeklyFormsCaseConfig(country='Mexico', utel_url='https://utel.test/', level='Licenciatura',
                                   modality='En linea', lead={})
    primary = {'status':'FAIL', 'error':'[inconcert_login] Sin sesión', 'utel_submission':'pending'}
    secondary = {'status':'FAIL', 'error':'[lead_balancer_search] No encontrado'}
    result = WeeklyFormsRunner._merge_dual_results(config, primary, secondary)
    assert result['error'] == '[inconcert_login] Sin sesión | [lead_balancer_search] No encontrado'
    assert result['utel_submission'] == 'pending'


def test_uncertain_signal_survives_dual_crm_and_phone_retry_wrappers(tmp_path):
    """Los wrappers no convierten la conciliación en un rechazo reintentable."""
    runner = WeeklyFormsRunner(Settings(storage_dir=tmp_path))
    runner._rotation_config = SimpleNamespace(weekly_form_type='footer', form_type='footer')
    runner._submission_attempted = True
    runner._surface_utel_feedback = AsyncMock()
    runner._retry_footer_submit_with_request_submit = AsyncMock()
    signal = UnconfirmedSubmission('utel_submit', 'HTTP 500. Error al enviar. Contacta a soporte.')
    with patch.object(UtelInconcertRunner, '_submit_utel_form', AsyncMock(side_effect=signal)) as submit:
        with pytest.raises(UnconfirmedSubmission):
            asyncio.run(runner._submit_utel_form(Mock(), Mock()))
        submit.assert_awaited_once()
    runner._retry_footer_submit_with_request_submit.assert_not_awaited()


def test_generic_lp_server_error_is_also_reconcilable(tmp_path):
    """Una LP genérica con POST y 5xx usa la misma protección contra duplicados."""
    async def scenario():
        runner = WeeklyFormsRunner(Settings(storage_dir=tmp_path))
        runner._rotation_config = SimpleNamespace(weekly_form_type='form_lp')
        runner._validate_generic_form = AsyncMock()
        handlers = {}
        request = SimpleNamespace(method='POST', url='https://landing.test/submit')

        async def click(**_kwargs):
            handlers['request'](request)
            handlers['response'](SimpleNamespace(request=request, status=500))

        submit = AsyncMock()
        submit.count.return_value = 1
        submit.is_visible.return_value = True
        submit.click.side_effect = click
        form = Mock()
        form.locator.return_value.first = submit
        page = Mock()
        page.on.side_effect = lambda name, handler: handlers.update({name:handler})
        with pytest.raises(UnconfirmedSubmission):
            await runner._submit_utel_form(page, form)
        submit.click.assert_awaited_once()
        assert runner._submission_attempted
    asyncio.run(scenario())


@pytest.mark.parametrize('markup', [
    '<li><span>Email</span></li>',
    '<button role="menuitem">Email <span>\uf0d7</span></button>',
])
def test_email_filter_accepts_icons_delayed_options_and_preserved_session(tmp_path, markup):
    """Dos búsquedas locales verifican el filtro real y no envían tráfico externo."""
    async def scenario():
        from playwright.async_api import async_playwright
        runner = WeeklyFormsRunner(Settings(storage_dir=tmp_path))
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route('**/*', lambda route: route.fulfill(status=200, content_type='application/json', body='{}'))
            await page.goto('https://crm.test/')
            await page.set_content('''
              <button id="filter">Nombre <span>\uf0d7</span></button>
              <ul class="dropdown-menu" role="menu" hidden></ul>
              <input placeholder="Ingrese un texto para buscar">
              <button title="Buscar" id="search">Buscar</button>
              <script>
                window.searches = [];
                document.querySelector('#filter').onclick = () => setTimeout(() => {
                  document.querySelector('ul').hidden = false;
                }, 150);
                document.querySelector('ul').onclick = () => {
                  document.querySelector('#filter').innerHTML = 'Email <span>\\uf0d7</span>';
                  document.querySelector('ul').hidden = true;
                };
                document.querySelector('#search').onclick = () => {
                  window.searches.push(document.querySelector('input').value);
                  fetch('/api/contact/get_contacts/', {method:'POST'});
                };
              </script>
            ''')
            await page.locator('ul').evaluate('(el, html) => el.innerHTML = html', markup)
            for email in ('original@example.test', 'siguiente@example.test'):
                await runner._apply_contact_search(page, 'Email', email)
            assert await page.evaluate('window.searches') == ['original@example.test', 'siguiente@example.test']
            assert (await page.locator('#filter').inner_text()).startswith('Email')
            await browser.close()
    asyncio.run(scenario())
