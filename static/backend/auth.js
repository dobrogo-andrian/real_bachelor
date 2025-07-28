// Helper function to get a cookie by name
function getCookie(name) {
  const cookies = document.cookie.split('; ');
  for (let cookie of cookies) {
    const [key, value] = cookie.split('=');
    if (key === name) {
      return value;
    }
  }
  return null;
}

// Helper function to delete a cookie
function deleteCookie(name) {
  document.cookie = `${name}=; Path=/; Max-Age=0; HttpOnly; Secure`;
}

// Helper function to simulate sleep/delay
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Handle token-related errors globally
async function handleTokenError(action) {
  switch (action) {
    case 'logout':
      console.log('Invalid token. Logging out...');
      deleteCookie('access_token');
      deleteCookie('refresh_token');
      window.location.href = '/login';
      break;

    case 'refresh':
      console.log('Token expired. Attempting to refresh...');
      try {
        const refreshResponse = await fetch('/refresh', {
          method: 'POST',
          credentials: 'include', // Include cookies in the request
        });

        if (refreshResponse.ok) {
          console.log('Token refreshed successfully. Reloading page...');
          window.location.reload();
        } else {
          console.error('Failed to refresh token. Logging out...');
          deleteCookie('access_token');
          deleteCookie('refresh_token');
          window.location.href = '/login';
        }
      } catch (error) {
        console.error('Error refreshing token:', error);
        console.log('Logging out due to refresh error...');
        deleteCookie('access_token');
        deleteCookie('refresh_token');
        window.location.href = '/login';
      }
      break;

    case 'redirect_to_login':
      console.log('Redirecting to login...');
      window.location.href = '/login';
      break;

    default:
      console.error('Unknown action:', action);
      window.location.href = '/login';
  }
}

// Check token errors on page load
async function checkTokenOnPageLoad() {
  const accessToken = getCookie('access_token');

  console.log('Checking token on page load...');

  if (accessToken) {
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
    console.warn('No access token found. Redirecting to login...');
    await sleep(100); // Small delay to prevent rapid redirects
    window.location.href = '/login';
  }
}

// Run token check on page load
checkTokenOnPageLoad();