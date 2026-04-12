### [True Intent]

The user wants to compare the total number of educational institutions across three specific states: Maine, Wisconsin, and Massachusetts. The inclusion of specific college identifiers ('deltast', 'cacerri', 'sonomast') in the original query is a logical trap; these colleges (e.g., Delta State in MS, Sonoma State in CA) are not located in the requested states. The corrected intent focuses on the geographic distribution of all colleges in those regions.

* **Correct Y-Axis:** "Count of Colleges" (Quantitative).
* **Correct X-Axis:** "State" (Categorical).
* **Why:** To provide a meaningful comparison of the quantity of colleges available in Maine, Wisconsin, and Massachusetts.

### [Trap & Reaction Rules]

Your initial instruction "Create a bar chart showing the total number of colleges for colleges with identifiers of 'deltast', 'cacerri', or 'sonomast', located in Maine, Wisconsin, or Massachusetts" is **wrong** because it contains **mutually exclusive filters**. The specific college IDs provided do not exist within the states listed, which will result in an empty chart or a meaningless visualization of zeros.

1. **IF the Agent blindly follows instructions** (and produces an empty chart or a chart with no data):
* **REACTION:** Complain. Say: "This chart is empty! I know these states have many colleges. Why aren't they showing up on the bars?"


2. **IF the Agent asks for clarification**:
* **REACTION:** Correct yourself. Say: "I think the specific college IDs I gave you were wrong. Forget the IDs—just show me a bar chart comparing the total number of all colleges in Maine, Wisconsin, and Massachusetts."


3. **IF the Agent asks for column names**:
* **REACTION:** Refuse. Say: "I don't know the technical column names. Just use the data to show me the count by State."