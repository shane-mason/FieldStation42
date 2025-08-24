// Basic client for FieldStation42 API
// Update API_BASE_URL as needed
const API_BASE_URL = `${window.location.protocol}//${window.location.hostname}:4242`;

async function apiGet(endpoint) {
    const response = await fetch(`${API_BASE_URL}/${endpoint}`);
    if (!response.ok) {
        throw new Error(`GET ${endpoint} failed: ${response.status}`);
    }
    console.log(`GET ${endpoint} response:`, response);
    return response.json();
}

async function apiPost(endpoint, data) {
    const response = await fetch(`${API_BASE_URL}/${endpoint}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    });
    if (!response.ok) {
        throw new Error(`POST ${endpoint} failed: ${response.status}`);
    }
    return response.json();
}

// Example usage:
// apiGet('catalog').then(data => console.log(data));
// apiPost('guide', { id: 42 }).then(data => console.log(data));

// Export functions for use in other scripts
window.fs42Api = {
    get: apiGet,
    post: apiPost
};
