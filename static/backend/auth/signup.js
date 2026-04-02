(function () {
  const form = document.getElementById('signup-form');
  const errorNode = document.getElementById('error-msg');

  if (!form || !errorNode) {
    return;
  }

  function setError(message) {
    errorNode.textContent = message || '';
    errorNode.style.display = message ? 'block' : 'none';
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    setError('');

    const username = document.getElementById('username')?.value.trim() || '';
    const email = document.getElementById('email')?.value.trim() || '';
    const password = document.getElementById('password')?.value || '';
    const confirmPassword = document.getElementById('confirmPassword')?.value || '';
    const instagramLogin = document.getElementById('instagramLogin')?.value.trim() || '';
    const instagramPassword = document.getElementById('instagramPassword')?.value || '';

    if (!username || !email || !password || !confirmPassword || !instagramLogin || !instagramPassword) {
      setError('Please fill out all fields.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    try {
      const response = await fetch('/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username,
          email,
          password,
          instagram_login: instagramLogin,
          instagram_password: instagramPassword,
        }),
      });
      const payload = await response.json().catch(() => ({}));

      if (response.ok) {
        window.location.href = '/login';
        return;
      }

      setError(payload.error || payload.message || 'Sign up failed.');
    } catch (_error) {
      setError('Network error. Please try again.');
    }
  });
})();
