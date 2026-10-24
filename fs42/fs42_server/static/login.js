window.fs42Common.initTheme();

function nextPage() {
    const next = new URLSearchParams(window.location.search).get('next') || '/';
    return next.startsWith('/') && !next.startsWith('//') ? next : '/';
}

document.getElementById('login-form').addEventListener('submit', async function (event) {
    event.preventDefault();
    const error = document.getElementById('login-error');
    error.textContent = '';

    const response = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: document.getElementById('api-key').value })
    });

    if (response.ok) {
        window.location.href = nextPage();
    } else if (response.status === 429) {
        error.textContent = 'Too many failed attempts - wait a few minutes and try again.';
    } else {
        error.textContent = 'That key is not correct.';
    }
});
