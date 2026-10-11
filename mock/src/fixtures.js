// Exact released response data only. HTTP routing and state belong to the
// integration contract, which must supply the lookup selectors explicitly.
export function createFixtureStore(document) {
  if (!document || !Array.isArray(document.customers)) {
    throw new TypeError("Fixture document must contain a customers array.");
  }
  const source = structuredClone(document);
  const customers = new Map();
  const fixtures = new Map();
  const records = [];
  const services = new Set();

  function visit(customerNo, service, value, selectors) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new TypeError("Service fixtures must be objects.");
    }
    if (Object.hasOwn(value, "http")) {
      if (!Number.isInteger(value.http) || value.http < 100 || value.http > 599) {
        throw new TypeError("Fixture HTTP status must be an integer from 100 to 599.");
      }
      if (Object.hasOwn(value, "delaySeconds") &&
          (typeof value.delaySeconds !== "number" || !Number.isFinite(value.delaySeconds) || value.delaySeconds < 0)) {
        throw new TypeError("Fixture delaySeconds must be a nonnegative finite number.");
      }
      const key = JSON.stringify([customerNo, service, ...selectors]);
      fixtures.set(key, value);
      records.push({ customerNo, service, selectors, fixture: value });
      return;
    }
    for (const [selector, child] of Object.entries(value)) {
      visit(customerNo, service, child, [...selectors, selector]);
    }
  }

  for (const customer of source.customers) {
    if (!customer || typeof customer.customerNo !== "string" || !customer.customerNo ||
        !customer.services || typeof customer.services !== "object" || Array.isArray(customer.services)) {
      throw new TypeError("Each fixture customer needs customerNo and a services object.");
    }
    if (customers.has(customer.customerNo)) {
      throw new TypeError("Duplicate fixture customer number: " + customer.customerNo);
    }
    customers.set(customer.customerNo, customer);
    for (const [service, value] of Object.entries(customer.services)) {
      services.add(service);
      visit(customer.customerNo, service, value, []);
    }
  }

  return Object.freeze({
    customerNumbers: () => [...customers.keys()],
    serviceNames: () => [...services],
    customer: (customerNo) => structuredClone(customers.get(customerNo)),
    entries: () => structuredClone(records),
    lookup(customerNo, service, selectors = []) {
      if (typeof customerNo !== "string" || typeof service !== "string" ||
          !Array.isArray(selectors) || selectors.some(selector => typeof selector !== "string")) {
        throw new TypeError("Fixture lookup needs string customer/service names and string selectors.");
      }
      return structuredClone(fixtures.get(JSON.stringify([customerNo, service, ...selectors])));
    },
  });
}
