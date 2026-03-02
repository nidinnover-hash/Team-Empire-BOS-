import { NidinBOSClient } from "../../typescript/dist/index.js";

const client = new NidinBOSClient({
  baseUrl: "https://your-host",
  apiKey: "nbos_...",
  onRequestEvent: (event) => {
    console.log(
      `[sdk] ${event.method} ${event.path} status=${event.statusCode} durationMs=${event.durationMs}`,
    );
  },
});

const me = await client.authMe();
console.log("Authenticated as:", me.email);
