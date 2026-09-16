# Business Understanding: AI-Driven Seclusion Risk Prediction

## Main Problem

Schools vary in their use of restrictive practices such as seclusion, with some student populations experiencing these practices at higher rates. Differences in institutional resources, staffing, training, and other school characteristics may be associated with these patterns and warrant further investigation.

**The Challenge:** Identifying which schools are at elevated risk of seclusion incidents so that proactive interventions (such as reallocating funds or staff) can be made *before* incidents occur.

---

## Key Stakeholders

| Stakeholder | Role |
|---|---|
| **Capital One & Break Through Tech** | Challenge sponsors and advisors evaluating the AI models |
| **School Districts & Administrators** | End-users who would deploy this model to allocate funding, staffing, and resources proactively |
| **Students** | Ultimate beneficiaries—specifically marginalized groups and students with disabilities disproportionately impacted by seclusion |
| **U.S. Department of Education (Office for Civil Rights)** | Providers of the Civil Rights Data Collection (CRDC) dataset |

---

## Research Questions

1. How do specific school resources (funding, staffing ratios, and teacher certification levels) correlate with the frequency of seclusion incidents?
2. Can school resource and institutional characteristics be used to predict which schools are at elevated risk of high seclusion rates?
3. Which school resource variables are most strongly associated with differences in seclusion rates and may represent actionable areas for further investigation?

---

## Project Success Metrics

### Technical Success
- Develop and evaluate a baseline predictive model for identifying schools at elevated seclusion risk using appropriate classification or regression metrics determined after the target distribution is understood.
- Potential metrics: Precision, Recall, F1 score, ROC-AUC / PR-AUC, MAE / RMSE (if predicting continuous rate). Final metric selection will occur after initial exploratory data analysis.

### Business & Impact Success
- Translate model and exploratory data analysis findings into evidence-informed resource considerations that stakeholders could investigate further.

---

## In Scope vs. Out of Scope

### ✅ In Scope
- Analyzing school-level CRDC data (2015–2022)
- Evaluating funding, staffing, and teacher certifications
- Identifying patterns and risk factors in seclusion rates
- Recommending areas for further investigation

### ❌ Out of Scope
- Analyzing individual, personally identifiable student records (data is perturbed for privacy)
- Tracking incidents in real-time
- Physically implementing interventions in actual schools
- Causal claims without stronger evidence

---

## Key Definitions (To Be Finalized)

**High Seclusion Risk & Unit of Analysis**: These will be clarified after reviewing the available data and examining the distribution of seclusion outcomes. Possibilities for "risk" include: any seclusion incident, seclusion count above a threshold, seclusion rate per 1,000 students, top percentile of schools, or increase compared with prior years. Unit of analysis (school-level, district-level, or combination) will also be determined based on data structure.
