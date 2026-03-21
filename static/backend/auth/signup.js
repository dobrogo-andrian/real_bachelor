document.getElementById('signup-form').addEventListener('submit', async function (e) {
  e.preventDefault();

  const username = document.getElementById('username').value.trim();
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value.trim();
  const confirmPassword = document.getElementById('confirmPassword').value.trim();
  const instagramLogin = document.getElementById('instagramLogin').value.trim();
  const instagramPassword = document.getElementById('instagramPassword').value;
  const errorMsg = document.getElementById('error-msg');

  if (!username || !email || !password || !confirmPassword || !instagramLogin || !instagramPassword) {
    errorMsg.textContent = 'Please fill out all fields.';
    errorMsg.style.display = 'block';
    return;
  }

  if (password !== confirmPassword) {
    errorMsg.textContent = 'Passwords do not match.';
    errorMsg.style.display = 'block';
    return;
  }

  try {
    const response = await fetch('http://localhost:5000/signup', {
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

    const data = await response.json();

    if (response.ok) {
      alert(data.message || 'Sign up successful!');
      window.location.href = '/login'; // або інша сторінка
    } else {
      errorMsg.textContent = data.message || 'Sign up failed.';
      errorMsg.style.display = 'block';
    }
  } catch (error) {
    errorMsg.textContent = 'Network error.';
    errorMsg.style.display = 'block';
  }
});
