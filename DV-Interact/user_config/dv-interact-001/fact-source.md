### [True Intent]
Although you asked for a "box plot of status", your ACTUAL goal is to see the distribution of **Money Owed ($)** for each status category.
- **Correct Y-Axis:** "Amount Due" (Continuous variable).
- **Correct X-Axis:** "Payment Status" (Binary variable: Paid vs Unpaid).
- **Why:** You want to see the range, median, and outliers of the debts.

### [Trap & Reaction Rules]
Your initial instruction "box plot for full payment status" is wrong because "Status" is just 0 or 1.
1. **IF the Agent blindly follows instructions** and plots the Status column (resulting in flat lines at 0 and 1):
   - **REACTION:** Complain. Say: "This chart looks weird. It's just two flat lines. I want to see the distribution of the money, not just 0 and 1!"
2. **IF the Agent asks for clarification** (e.g., "Status is binary, what should be on the Y-axis?"):
   - **REACTION:** Correct yourself. Say: "Oh, sorry. I messed up. I meant I want to compare the **Total Amount Due** based on the payment status."
3. **IF the Agent asks for column names**:
   - **REACTION:** Refuse. Say: "I don't know the technical column names. Just show me the Amounts."