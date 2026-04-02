(function () {
  const loginForm = document.getElementById('login-form');
  const errorNode = document.getElementById('error-msg');
  const nextUrl = new URLSearchParams(window.location.search).get('next') || '/';

  if (!loginForm || !errorNode) {
    return;
  }

  function setError(message) {
    errorNode.textContent = message || '';
    errorNode.style.display = message ? 'block' : 'none';
  }

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setError('');

    const username = document.getElementById('username')?.value || '';
    const password = document.getElementById('password')?.value || '';

    try {
      const response = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const payload = await response.json().catch(() => ({}));

      if (response.ok) {
        window.location.href = nextUrl;
        return;
      }

      setError(payload.error || 'Login failed.');
    } catch (_error) {
      setError('Network error. Please try again.');
    }
  });
})();
