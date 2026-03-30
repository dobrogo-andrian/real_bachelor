const loginForm = document.getElementById('login-form');
const nextUrl = new URLSearchParams(window.location.search).get('next') || '/'; // Get 'next' from query params
const session = window.CommentLabSession;

// Handle token-related errors globally
// Handle token-related errors globally
async function handleTokenError(action) {
switch (action) {
  case 'logout':
    // Delete cookies and redirect to login
    session.clearSessionCookies();
    window.location.href = '/login';
    break;

  case 'refresh':
    // Attempt to refresh the token
    try {
      const refreshResponse = await session.fetchWithCsrf(
        '/refresh',
        {
          method: 'POST',
        },
        { refresh: true }
      );

      if (refreshResponse.ok) {
        console.log('Token refreshed successfully');
        // Retry the original request or reload the page
        window.location.reload();
      } else {
        console.error('Failed to refresh token');
        // Redirect to login if refresh fails
        window.location.href = '/login';
      }
    } catch (error) {
      console.error('Error refreshing token:', error);
      window.location.href = '/login';
    }
    break;

  case 'redirect_to_login':
    // Redirect to login
    window.location.href = '/login';
    break;

  default:
    console.error('Unknown action:', action);
    window.location.href = '/login';
}
}


// Check token errors on page load
// Check token errors on page load
async function checkTokenOnPageLoad() {
const hasAccessSession = session.hasAccessSession();

// Helper function to simulate sleep/delay
function sleep(ms) {
return new Promise(resolve => setTimeout(resolve, ms));
}

console.log('Checking token on page load...');

if (hasAccessSession) {
try {
  // Make a test request to validate the token
  const response = await fetch('/user-info', {
    method: 'GET',
    credentials: 'include', // Include cookies in the request
    headers: {
      'Accept': 'application/json', // Indicate that this is an API call
    },
  });

  if (response.status === 401) {
    // Handle token-related errors
    const data = await response.json();
    console.error('Token error on page load:', data);

    // Redirect or logout based on the server's action
    await handleTokenError(data.action);
  } else if (!response.ok) {
    // Log unexpected errors and redirect to login
    console.error('Unexpected error on page load:', response.statusText);
    console.log('Redirecting to login due to unexpected error...');
    await sleep(100); // Small delay to prevent rapid redirects
    window.location.href = '/login';
  } else {
    console.log('Token is valid. Proceeding...');
    // Token is valid, proceed with the page load
  }
} catch (error) {
  // Handle network or other unexpected errors
  console.error('Error validating token on page load:', error);
  console.log('Redirecting to login due to validation error...');
  await sleep(100); // Small delay to prevent rapid redirects
  window.location.href = '/login';
}
} else {
// No token found, log the issue and redirect to login
console.warn('No access token found. Redirecting to login...');
}
}

// Run token check on page load
checkTokenOnPageLoad();

// Handle login form submission
loginForm.addEventListener('submit', async (event) => {
event.preventDefault(); // Prevent the default form submission

const username = document.getElementById('username').value;
const password = document.getElementById('password').value;

try {
  // Send login request
  const response = await fetch('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });

  if (response.ok) {
    // Wait for the server to set the cookies
    const data = await response.json();
    console.log('Login successful, redirecting to:', nextUrl); // Debug: Check redirect URL

    // Redirect to the original page (nextUrl)
    window.location.href = nextUrl;
  } else if (response.status === 401) {
    // Handle login errors
    const data = await response.json();
    const errorMsg = document.getElementById('error-msg');
    errorMsg.textContent = data.error || 'Invalid username or password.';
    errorMsg.style.display = 'block'; // Show the error message
  } else {
    // Handle other errors
    const errorMsg = document.getElementById('error-msg');
    errorMsg.textContent = 'An error occurred. Please try again.';
    errorMsg.style.display = 'block'; // Show the error message
  }
} catch (error) {
  console.error('Login failed:', error);
  alert('An error occurred. Please try again.');
}
});
