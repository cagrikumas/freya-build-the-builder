import fixtures from "../fixtures/test-customers.json" with { type: "json" };
import { createBankWorker } from "./bank.js";

export default createBankWorker(fixtures);
