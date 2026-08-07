---

> ## Challenge Advisor: Update & Finalize Your Project Overview
>
> > 💡 **These grey text instructions are just for you, the team's Challenge Advisor; please delete them once you have completed the steps below.**
>
> We've pre-populated this Challenge Project Overview page — which is what will be shared with your Break Through Tech student team in August — using the details from your submission form. You should have received an email inviting you to join this repo as a Collaborator, enabling you to add files and make edits.
> 
> In order for your project to be finalized and assigned to a team, please:
> 1. **Review all sections below** and update or expand any content as needed, ensuring you address the SME Feedback in the section immediately below. Look for square brackets to find the places below that require additional inputs from you (e.g., "About [Company / Org Name]").
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
In this project, you will use district-level seclusion data and school resource datasets (funding, staffing ratios, and teacher certification levels) and Predictive Modeling / Recommender Systems to recommend proactive institutional interventions—such as targeted de-escalation training or specific sensory-room funding—to schools at high risk of seclusion incidents. This will help address the systemic root causes of restrictive practices by providing administrators with actionable "early warning" recommendations before crisis incidents occur.

### Success Criteria
Success will be measured by the Actionability Score of the model. A successful outcome is a Policy Recommendation Dashboard where an administrator can see a list of schools ranked by risk, and for each school, the top 3 AI-suggested interventions (e.g., "Implement PBIS Training Level 2" or "Decrease Student-to-Teacher Ratio in Grade 2") that the data predicts will most effectively reduce restrictive practices.

### Stretch Goals
- LLM "Intervention Drafter": An LLM that takes the model's data and automatically drafts a Grant Proposal or Budget Request to fund the suggested intervention (e.g., asking for funds for a new sensory room).
- Cost-Benefit Analysis: A module that calculates the "Cost of Seclusion" (staff turnover, legal risk, student trauma) vs. the "Cost of Prevention" to help schools justify the investment in better support.
  
### Project Milestones

Use these milestones to guide your work. Your team will create a **GitHub Projects board** to track tasks within each milestone.

| Month | Milestone | Key Activities |
|---|---|---|
| September | Feature Engineering for Solutions | Students will merge seclusion data with "Environmental Factors" (e.g., Is there a behavior specialist on-site? What is the average teacher experience level?). They will create a "Resource Gap" score for every school. |
| October | Prescriptive Modeling | Students will build a Random Forest or XGBoost model to rank which environmental factors most strongly correlate with a reduction in seclusion. They will begin building a Recommender System that matches a school's specific risk profile with a successful intervention strategy used by a high-performing peer school. |
| November | Outcome Simulation | Students will create a "What-If" simulator. For example: "If this school adds one more behavior-certified aide, how much is the seclusion risk predicted to drop?" They will evaluate the model using Precision-Recall to ensure they aren't recommending expensive interventions where they aren't needed. |

> **Note for the team:** Please create a GitHub Projects board in this repository to break these milestones into weekly tasks. Go to the **Projects** tab → **New project** → Choose **Board** → Add columns for each month.

---

## 📊 Dataset

**Name and Source:** District-level seclusion data and school resource datasets from the Civil Rights Data Collection (CRDC)  
**Format:** CSV
**Size:** Less than 5 GB  
**Location:** https://catalog.data.gov/dataset/civil-rights-data-collection-crdc

### Key Details
- [Brief description of what's in the data]
- [Any known limitations or preprocessing needed]
- [Link to data dictionary or documentation, if available]

---

## 🛠️ Suggested Approach

**ML Problem Type:** Classification, Recommendation Systems, Computer Vision, Deep Learning / Neural Networks, Transfer Learning / Pre-trained Models, Ethical AI, Predictive Modeling

**Recommended Libraries:**
- [e.g., pandas, scikit-learn, TensorFlow, Hugging Face]

**Evaluation Metrics:**
- [e.g., Accuracy, Precision/Recall, RMSE, BLEU score]

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

**Official check-ins:** During our biweekly 45-minute AI Studio Lab Section meeting block (2nd and 4th week of every month)

 **Other ways to reach out to me with questions:** 
* [e.g., Your team's channel within Break Through Tech’s Discord space]
* [e.g., Email; please copy your teammates and AI Studio Coach]
* [e.g., Request a team check-in on Zoom]
* [Note: I will aim to respond within 48 hours. Please reach out to your AI Studio Coach with urgent questions.]

> 💡 **Challenge Advisor: Please update the above based on your availability and preference. If you are not able to answer questions or meet with fellows outside of the biweekly Lab Section check-ins, simply write in "N/A (only available during the official check-in times)"**

**Recommended free coding / collaboration tools**
* […]
* […]

---

## 🚀 Getting Started

1. **Review this overview document** and note any questions for our first meeting
2. **Begin reviewing the dataset** using the link above
3. **Read the GitHub Projects documentation** [here](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)

I’m excited to work with you!

---

## ❓ Questions?

Please bring any questions to our first meeting during the week of August 24th (Break Through Tech’s Bridge to Studio - Session C). 
