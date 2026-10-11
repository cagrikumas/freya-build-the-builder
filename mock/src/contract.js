// Test-environment routing from the released 2026-10-01 service contract, §5–6,
// and test-environment/test-customers.md. These are mock facts, never builder rules.
export const SERVICES = Object.freeze({
  "cards.list": { required: ["customerNo"], selectors: [], customer: true,
    notFound: ["FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."] },
  "cards.balance": { required: ["cardNumber"], selectors: ["cardNumber"],
    notFound: ["FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı"] },
  "statement.week.get": { required: ["cardNumber"], selectors: ["cardNumber"],
    notFound: ["FB_IVR_CHANNEL_121", "Kart bulunamadı"] },
  "statement.week.decide": { required: ["cardNumber", "newStatementWeek", "statementDay"],
    selectors: ["cardNumber", "newStatementWeek"] },
  "statement.week.change": { required: ["cardNumber", "newStatementWeek", "statementDay"],
    selectors: ["cardNumber", "newStatementWeek"] },
  "contact.email.get": { required: ["customerNo", "intAddressInfoType"], selectors: [], customer: true },
  "statement.pdf.send": { required: ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"],
    selectors: [], customer: true, notFound: ["FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"] },
});
