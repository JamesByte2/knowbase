import axios from "axios";

export const client = axios.create({ baseURL: "/api" });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(undefined, (error) => {
  if (error.response?.status === 401) {
    localStorage.removeItem("token");
    window.location.hash = "#/login";
  }
  return Promise.reject(error);
});

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
  created_at: number;
}
