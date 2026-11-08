# Personal Expense Management Agent — Reproducible Demo

Offline deterministic run: transaction and memory tools are real; LLM responses are scripted so no API key or network call is required.

### A. Short-term conversational context

```json
{
  "turn_1": "October Dining Out spending was PKR 28,300.",
  "turn_2": "September was PKR 13,950; October was PKR 14,350 higher.",
  "turn_3": {
    "biggest_transaction": {
      "date": "2026-10-09",
      "merchant": "KFC",
      "amount_pkr": 2850.0,
      "category": "Dining Out"
    },
    "source": "data/transactions.csv"
  }
}
```

### B. Long-term memory across sessions

```json
{
  "session_1_confirmed_budget": {
    "saved": true,
    "kind": "budget",
    "key": "Dining Out",
    "value": 15000.0
  },
  "session_1_confirmed_goal": {
    "saved": true,
    "kind": "goal",
    "key": "emergency fund",
    "value": "6 months"
  },
  "session_2_recalled": {
    "user_id": "demo_alice",
    "profile": {},
    "budgets": {
      "Dining Out": 15000.0
    },
    "goals": {
      "emergency fund": "6 months"
    },
    "notes": []
  },
  "session_2_budget_check": {
    "category": "Dining Out",
    "month": "2026-10",
    "budget_pkr": 15000.0,
    "spent_pkr": 28300.0,
    "remaining_pkr": -13300.0,
    "percent_used": 188.67,
    "status": "overspent",
    "days_elapsed": 31,
    "days_in_month": 31,
    "month_elapsed_percent": 100.0,
    "pace": "ahead of pace",
    "source": "data/transactions.csv"
  }
}
```

### C. RAG-grounded finance concepts and out-of-scope request

```json
[
  {
    "question": "What is the 50/30/20 rule?",
    "sources": [
      "01_budgeting_methods.md"
    ],
    "backend": "keyword fallback (Chroma index not built)",
    "retrieved_chunks": [
      {
        "content": "# Budgeting Methods: 50/30/20, Zero-Based and Envelope\n\n## 50/30/20 rule\nSplit take-home income into three buckets: 50% needs (rent, utilities, groceries, transport, minimum debt payments), 30% wants (dining out, entertainment, shopping, hobbies), 20% savings and extra debt repayment. It is a starting point; in high-rent cities the needs share may reach 60% and wants must shrink.",
        "source": "01_budgeting_methods.md",
        "chunk_id": 0,
        "score": 4
      },
      {
        "content": "## Envelope method\nEach category gets a fixed amount (physically or virtually). When an envelope is empty, spending in that category stops or is covered by explicitly moving money from another envelope. Works well for volatile categories such as dining out and shopping.\n\n## Choosing a method\n- Beginners with stable salary: 50/30/20.\n- Freelancers or variable income: zero-based.\n- Chronic overspending in one category: envelope.",
        "source": "01_budgeting_methods.md",
        "chunk_id": 2,
        "score": 3
      }
    ],
    "scripted_answer": "The retrieved guidance is summarized below; see the listed source file(s)."
  },
  {
    "question": "How big should my emergency fund be?",
    "sources": [
      "03_emergency_fund_and_savings.md"
    ],
    "backend": "keyword fallback (Chroma index not built)",
    "retrieved_chunks": [
      {
        "content": "# Emergency Fund and Savings Goals\n\n## Why\nAn emergency fund covers job loss, medical bills or urgent repairs without borrowing.\n\n## How much\nCommon guidance: 3 months of essential expenses for people with stable salaried jobs, 6 months for freelancers, single-income households or dependants. Essential expenses = rent + utilities + groceries + transport + minimum debt payments + insurance.",
        "source": "03_emergency_fund_and_savings.md",
        "chunk_id": 0,
        "score": 2
      }
    ],
    "scripted_answer": "The retrieved guidance is summarized below; see the listed source file(s)."
  },
  {
    "question": "Avalanche vs snowball?",
    "sources": [
      "04_debt_management.md"
    ],
    "backend": "keyword fallback (Chroma index not built)",
    "retrieved_chunks": [
      {
        "content": "# Debt Repayment Strategies\n\n## Avalanche method\nPay minimums on all debts, put any extra money on the debt with the highest interest rate. Minimises total interest paid.\n\n## Snowball method\nPut extra money on the smallest balance first. Costs more interest but gives quick wins that help motivation.",
        "source": "04_debt_management.md",
        "chunk_id": 0,
        "score": 2
      },
      {
        "content": "## Rules\n- Never skip minimum payments; late fees and penalty rates compound the problem.\n- Credit card revolving balances usually carry the highest rates, so they come first under avalanche.\n- Avoid taking new debt to repay old debt unless the new rate is clearly lower and fees are included in the comparison.\n- Debt payments above 36% of gross income are generally considered a warning sign.",
        "source": "04_debt_management.md",
        "chunk_id": 1,
        "score": 1
      }
    ],
    "scripted_answer": "The retrieved guidance is summarized below; see the listed source file(s)."
  },
  {
    "question": "Which stock should I buy?",
    "answer": "I can’t recommend specific investments; that is outside my scope, and the supplied documents do not cover stock picks."
  }
]
```

### D. MCP anomaly tool

```json
{
  "tool": "detect_anomalies",
  "args": {
    "month": "2026-10"
  },
  "result": [
    {
      "type": "transaction_over_3x_category_median",
      "date": "2026-10-20",
      "merchant": "Daraz",
      "amount_pkr": 98000.0,
      "category": "Shopping",
      "category_median_pkr": 13975.0
    },
    {
      "type": "possible_duplicate",
      "date": "2026-10-21",
      "merchant": "Foodpanda",
      "amount_pkr": 2150.0,
      "other_date": "2026-10-21",
      "other_amount_pkr": 2150.0
    }
  ],
  "agent_response": [
    "The tool shows a Daraz charge of PKR 98,000 on 2026-10-20, which is much higher than the category median. Was this expected?",
    "It also shows two Foodpanda charges of PKR 2,150 on 2026-10-21. Could you check whether both are valid?"
  ]
}
```

### E. Planning and replanning after a change

```json
{
  "plan_before_change": [
    "Get October category totals from monthly_summary.",
    "Retrieve cost-saving guidance from search_knowledge_base.",
    "Identify candidate reductions totaling PKR 10,000; ask before any action."
  ],
  "tools_used": {
    "monthly_summary": 323900.0,
    "saving_tip_sources": [
      "07_cost_saving_tips.md",
      "01_budgeting_methods.md"
    ]
  },
  "change_event": "Actually my rent just went up by PKR 5,000.",
  "plan_after_change": [
    "Update the rent assumption by +PKR 5,000 only after confirmation.",
    "Find PKR 15,000 of cuts to offset the rent increase and still reduce total spending by PKR 10,000.",
    "Use the October summary and retrieved tips; present options and ask before saving."
  ],
  "confirmation": "Please confirm before the rent assumption is saved.",
  "staged_change_not_applied": {
    "saved": false,
    "confirmation_required": true,
    "proposed": {
      "kind": "profile",
      "key": "monthly_rent_increase_pkr",
      "value": "5000"
    }
  }
}
```

### F. Error handling

```json
{
  "invalid_month": {
    "error": "Invalid month; expected YYYY-MM with a valid month from 01 to 12."
  },
  "missing_csv": {
    "error": "Transaction file not found: missing.csv"
  },
  "empty_retrieval": {
    "query": "quasars and black holes",
    "results": [],
    "sources": [],
    "backend": "keyword fallback (Chroma index not built)"
  },
  "simulated_llm_retry": {
    "first_error": "simulated temporary model API error",
    "retry_result": "retry succeeded"
  }
}
```

### G. Human oversight

```json
{
  "request": "Change the Dining Out budget to PKR 17,000.",
  "agent_response": "I can change it from PKR 15,000 to PKR 17,000 after your explicit confirmation. Should I save this?",
  "staged_change": {
    "saved": false,
    "confirmation_required": true,
    "proposed": {
      "kind": "budget",
      "key": "Dining Out",
      "value": "17000"
    }
  },
  "budget_before": {
    "category": "Dining Out",
    "amount": 15000.0
  },
  "budget_after_without_confirmation": {
    "category": "Dining Out",
    "amount": 15000.0
  }
}
```
