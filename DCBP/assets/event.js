const theme = document.getElementById('theme-toggle');
if (location.pathname === '/' || location.pathname.endsWith('/index.html')) {
  const legacy = { '#about': 'about.html', '#events': 'events.html', '#board': 'board.html', '#join': 'get-involved.html', '#contact': 'get-involved.html#contact' };
  if (legacy[location.hash]) location.replace(legacy[location.hash]);
}
theme?.addEventListener('click', () => {
  const value = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = value;
  try { localStorage.setItem('theme', value); } catch {}
});

const copy = document.getElementById('copy');
copy?.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText('phdcoalition.dcbp@unibe.ch'); copy.textContent = 'Copied'; }
  catch { copy.textContent = 'phdcoalition.dcbp@unibe.ch'; }
});

const panel = document.querySelector('[data-rsvp-event]');
if (panel) {
  const buttons = [...panel.querySelectorAll('[data-status]')];
  const remove = panel.querySelector('[data-remove]');
  const message = panel.querySelector('[role=status]');
  const endpoint = `/api/rsvp?event=${encodeURIComponent(panel.dataset.rsvpEvent)}`;
  function render(data) {
    for (const status of ['coming', 'interested']) {
      panel.querySelector(`[data-count="${status}"]`).textContent = data.counts[status];
      panel.querySelector(`[data-status="${status}"]`)?.setAttribute('aria-pressed', String(data.status === status));
    }
    remove.hidden = !data.status;
  }
  async function update(status, initial = false) {
    buttons.forEach(button => button.disabled = true);
    remove.disabled = true;
    message.textContent = initial ? 'Loading responses…' : 'Saving your response…';
    try {
      const response = await fetch(endpoint, initial ? { cache: 'no-store' } : {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ status }), cache: 'no-store'
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      render(data);
      message.textContent = initial
        ? (data.status ? `Your response: ${data.status === 'coming' ? 'coming' : 'interested'}.` : 'Let us know so we can plan.')
        : (data.status ? 'Thanks, your response is saved. You can change it any time.' : 'Your response has been removed.');
    } catch {
      message.textContent = initial ? 'Responses are unavailable right now. Please try again.' : 'Your response could not be confirmed. Please try again.';
    } finally {
      buttons.forEach(button => button.disabled = false);
      remove.disabled = false;
    }
  }
  buttons.forEach(button => button.addEventListener('click', () => update(button.dataset.status)));
  remove.addEventListener('click', () => update(null));
  update(null, true);
}

document.querySelectorAll('[data-email-updates]').forEach(emailForm => {
  emailForm.addEventListener('submit', event => {
    const choice = emailForm.querySelector('input[type="checkbox"][name="event-updates"]') || emailForm.querySelector('input[name="future-events"]');
    const future = emailForm.querySelector('input[name="future-events"]');
    choice.setCustomValidity(choice.checked || future?.checked ? '' : 'Choose which updates you would like.');
    if (!emailForm.reportValidity()) event.preventDefault();
  });
  emailForm.addEventListener('change', () => emailForm.querySelectorAll('input[type="checkbox"]').forEach(input => input.setCustomValidity('')));
});

// Display the same shared attendance totals on the homepage cards.
async function loadCardCounts() {
  for (const card of document.querySelectorAll('[data-counts-event]')) {
    try {
      const response = await fetch(`/api/rsvp?event=${encodeURIComponent(card.dataset.countsEvent)}`, { cache: 'no-store' });
      if (!response.ok) throw new Error();
      const { counts } = await response.json();
      card.textContent = `${counts.coming} coming · ${counts.interested} interested`;
    } catch { card.textContent = 'See attendance on the event page'; }
  }
}
loadCardCounts();
