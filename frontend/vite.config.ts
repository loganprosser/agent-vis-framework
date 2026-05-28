import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.AGENTIC_WORKFLOW_API_PROXY ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.FRONTEND_PORT ?? "5173"),
    proxy: {
      "/health": backend,
      "/workflows": backend,
      "/runs": backend,
    },
  },
});
