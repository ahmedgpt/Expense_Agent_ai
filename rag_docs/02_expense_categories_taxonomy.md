# Expense Category Taxonomy and Classification Rules

Use exactly these categories: Groceries, Dining Out, Transport, Utilities, Rent, Health, Education, Entertainment, Shopping, Subscriptions, Savings/Investments, Debt Payments, Transfers, Other.

## Rules of thumb
- Supermarkets, vegetable and grocery stores (e.g. Imtiaz, Carrefour, Al-Fatah) -> Groceries.
- Restaurants, cafes, food delivery apps (Foodpanda, KFC, Hardee's, Starbucks) -> Dining Out.
- Fuel, ride-hailing (Careem, Uber, inDrive), parking, bus/metro cards -> Transport.
- Electricity, gas, water, internet, mobile top-up (K-Electric, LESCO, SNGPL, PTCL, Jazz, Zong) -> Utilities.
- Netflix, Spotify, YouTube Premium, cloud storage, app subscriptions -> Subscriptions (not Entertainment).
- Pharmacies, clinics, hospitals, lab tests -> Health.
- Tuition, books, course platforms -> Education.
- Clothes, electronics, online marketplaces (Daraz) -> Shopping.
- Person-to-person transfers and wallet top-ups -> Transfers.

## Ambiguity handling
If a merchant could belong to two categories (e.g. a hypermarket selling groceries and clothes), choose the dominant one, record confidence as low and ask the user to confirm. Never silently guess for amounts above PKR 20,000.
