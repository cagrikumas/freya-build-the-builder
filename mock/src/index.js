// Infrastructure only. Implement the bank's contract from the released case.
// This placeholder is intentionally not a working bank and must not be submitted.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") {
      return Response.json({ status: "awaiting_case_contract", ready: false });
    }
    return Response.json({ error: "The bank service contract has not been loaded." }, { status: 503 });
  }
};
