import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/upload": "http://localhost:8000",
      "/sse": "http://localhost:8000",
      "/analysis": "http://localhost:8000",
      "/generate": "http://localhost:8000",
      "/thumbnails": "http://localhost:8000",
      "/download": "http://localhost:8000",
      "/correction-video": "http://localhost:8000",
      "/correction-frame": "http://localhost:8000",
      "/corrections": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
