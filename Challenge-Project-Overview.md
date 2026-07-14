---

> ## Challenge Advisor: Update & Finalize Your Project Overview
>
> > 💡 **These grey text instructions are just for you, the team's Challenge Advisor; please delete them once you have completed the steps below.**
>
> We've pre-populated this Challenge Project Overview page — which is what will be shared with your Break Through Tech student team in August — using the details from your submission form. You should have received an email inviting you to join this repo as a Collaborator, enabling you to add files and make edits.
> 
> In order for your project to be finalized and assigned to a team, please:
> 1. **Review all sections below** and update or expand any content as needed, making sure to address the SME Feedback in the section immediately below. Look for square brackets to find the places below that require additional inputs from you (e.g., "About [Company / Org Name]").
> 2. **Add your dataset** to the [data folder](data) in this repo.
> 3. **Close the Issue assigned to you in this repo** to let us know that you have made your edits and the overview page is ready for final review. You can do this by going to the _Issues_ tab in the top left section of the menu above, add a comment that says "CA review complete", and click the button to Close the Issue. 
>
> If you're unfamiliar with how to edit a page like this in GitHub, check out [this tutorial](https://ubc-lib-geo.github.io/gis-workshop-waml-template/content/handson/edit-readme.html) for a quick overview (start with step 2 and only edit this page), and [this guide](https://ubc-lib-geo.github.io/gis-workshop-waml-template/content/markdown.html) on how to use Markdown to compose text.
>
>
> ❌ Remember that this is a public repo. Do NOT include: Proprietary data, PII, API keys, credentials, or anything confidential.
---

## 📋 BTT Internal Evaluation Notes
*(This section is for BTT staff only — remove before sharing with students)*

| Check | Status | Notes |
|-------|--------|-------|
| Python Compatibility | 🟡 | The submission mentions the use of Python-based libraries like Random Forest and XGBoost, but incorporates complex elements such as LLMs and deep learning which may necessitate a more advanced setup than what's typical for ML Foundations graduates. Overall, the project requires thorough vetting to ensure that all tools are accessible within a Python environment. |
| Data Readiness | 🟡 | The project relies on datasets from the Civil Rights Data Collection. While these datasets might be useful, their readiness is uncertain, as the data size is unknown and no indication of preprocessing has been provided. This poses a risk that substantial cleaning efforts will be required. |
| Resource Check | 🟢 | The project appears to only require Google Colab free tier, which is accessible to students, mitigating any risks associated with proprietary software or specialized hardware beyond standard availability. |

**Student Fit Score:** 5/10  
**Technical Depth Score:** 6/10  
**Overall Recommendation:** REVISE

**Advisor Feedback Draft:**
The project addresses a high-impact social issue with strong potential for interpretability, which is a core strength. To align with our 12-week timeline, I recommend two technical adjustments: 1. Reserving the 'Computer Vision' component for stretch goals and instead focusing on tabular predictive modeling using XGBoost or fundamental Deep Learning algorithms; 2. Restrict the LLM intervention component to a static template generator rather than an agentic flow to ensure deterministic, more reliable outputs.
---

# AI-Driven Resource Allocation to Reduce Restrictive Practices

**Company / Org:** Other  
**Challenge Advisor:** Caroline Bell, carolineloubell@gmail.com  
**Program:** Break Through Tech AI Studio - Fall 2026

---

## 🏢 About Other

Other focuses on using data-driven approaches in the education sector to improve student outcomes and reduce restrictive practices through informed decision-making.

---

## 🎯 The Challenge

### Project Summary
Using district-level seclusion data and school resource datasets (funding, staffing ratios, and teacher certification levels) and Predictive Modeling / Recommender Systems to recommend proactive institutional interventions to schools at high risk of seclusion incidents. This helps address the systemic root causes of restrictive practices by providing administrators with actionable early warning recommendations before crisis incidents occur.

### Success Criteria
Actionability Score of the model, Precision-Recall evaluation

### Project Milestones

Use these milestones to guide your work. Your team will create a **GitHub Projects board** to track tasks within each milestone.

| Month | Milestone | Key Activities |
|-------|-----------|----------------|
| **September** | Data Understanding | Explore dataset, handle missing values, document findings |
| **October** | Model Development | Train baseline model, experiment with approaches, iterate |
| **November** | Evaluation & Presentation | Finalize model, prepare presentation, document results |

> **Note for the team:** Please create a GitHub Projects board in this repository to break these milestones into weekly tasks. Go to the **Projects** tab → **New project** → Choose **Board** → Add columns for each month.

---

## 📊 Dataset

**Name and Source:** District-level seclusion data and school resource datasets from the Civil Rights Data Collection (CRDC)  
**Format:** CSV  
**Size:** unknown  
**Location:** [Link to dataset or instructions for accessing it]

### Key Details
- District-level seclusion data and school resource datasets including funding, staffing ratios, teacher certification levels, and environmental factors (behavior specialist presence, teacher experience).
- [Any known limitations or preprocessing needed]
- [Link to data dictionary or documentation, if available]

---

## 🛠️ Suggested Approach

**ML Problem Type:** Classification, Recommender Systems

**Recommended Libraries:**
- Random Forest
- XGBoost
- Recommender Systems
- LLM (Intervention Drafter)
- Classification
- Computer Vision
- Deep Learning / Neural Networks
- Transfer Learning / Pre-trained Models
- Predictive Modeling
- Google Colab

**Evaluation Metrics:**
- Actionability Score, Precision-Recall

---

## 📚 Resources to Get Started

The following resources will help your team understand the problem space and potential technical approaches for this project:

**Background Reading:**
- [Link to an article or blog post about the problem domain]
- [Link to an industry report or case study]

**Technical Tutorials:**
- [Link to a free tutorial on the ML technique(s) involved]
- [Link to documentation for a key library or tool]

**Code Examples:**
- [Link to a relevant GitHub repo]
- [Link to a sample implementation or starter code]

**Other:**
- [Links to any additional resources — e.g., papers, videos, podcasts, etc.]

*Feel free to explore beyond these, and share anything interesting you find with me!*

---

## 🤝 How We'll Work Together

**Check-ins:** During our biweekly 60-min AI Studio Lab Section meeting block (2nd and 4th week of every month)  
**Communication:** Slack (Break Through Tech workspace)  
**Response time:** Within 48 hours on weekdays  

**Recommended Tools:**
- **Coding:** Google Colab
- **Collaboration:** GitHub, Notion
- **Virtual Meetings:** Zoom, Google Meet

---

## 🚀 Getting Started

1. **Review this overview document** and note any questions for our first meeting
2. **Begin reviewing the dataset** using the link above
3. **Read the GitHub Projects documentation** [here](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)

I'm excited to work with you!

---

## ❓ Questions?

Please bring any questions to our first meeting during the week of August 24th (Break Through Tech's Bridge to Studio - Session B).
