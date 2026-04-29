const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export async function getHealth() {
  const response = await fetch(`${BASE_URL}/health/`);
  if (!response.ok) {
    throw new Error('Failed to reach API');
  }
  return response.json();
}
