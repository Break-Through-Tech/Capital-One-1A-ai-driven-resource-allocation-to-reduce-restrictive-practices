# Capital One 1A: AI-Driven Resource Allocation to Reduce Restrictive Practices

## Project Overview

This project is part of the **Break Through Tech AI Studio** in collaboration with **Capital One**.

Our team is exploring how data and machine learning can be used to better understand patterns in restrictive practices and school resource availability.

The goal of the project is to investigate relationships between school characteristics, available resources, and restrictive-practice outcomes in order to support more informed and equitable resource allocation decisions.


## Problem Statement

Restrictive practices, including practices such as seclusion, may vary across schools and districts based on a variety of factors.

At the same time, schools differ in characteristics such as:

- Student enrollment
- Staffing levels
- Counseling resources
- Special education populations
- Available school resources
- District characteristics

Our project aims to analyze these factors and identify patterns that may help inform how resources could be allocated to reduce unnecessary restrictive practices.


## Dataset

The project uses publicly available school-level data from the **Civil Rights Data Collection (CRDC)**, a biennial survey administered by the U.S. Department of Education. The CRDC covers public schools and districts nationwide and includes information on student enrollment, school characteristics, staffing, educational programs, discipline, and restraint and seclusion.

We are working with the following collection years:

| School Year |
|---|
| 2021–22 |
| 2020–21 |
| 2017–18 |
| 2015–16 |

Files are downloaded as CSVs from [Data.gov](https://catalog.data.gov/dataset/civil-rights-data-collection-crdc). Variable definitions differ by year, so each collection's data definitions and documentation should be reviewed before analysis. Additional CRDC background is available from the [U.S. Department of Education CRDC page](https://www.ed.gov/laws-and-policy/civil-rights-laws/civil-rights-data-collection-crdc/civil-rights-data).

Known limitations include missing or suppressed values, differences in reporting across schools and years, and the observational nature of the data. Findings should be interpreted as associations, not as evidence that a particular resource or intervention causes a reduction in restrictive practices.


## Project Goals

The project currently focuses on:

1. Understanding the project problem and relevant stakeholders
2. Auditing and organizing available datasets
3. Cleaning and preprocessing project data
4. Engineering meaningful school and resource-related features
5. Conducting exploratory data analysis (EDA) and baseline analyses
6. Identifying relationships between school resources and restrictive practices
7. Preparing the data and insights for future predictive modeling

## Team members 

| Name | Github Handle |  |
| -- | -- | -- |
| Adhya Reddy Putta | @adhya-putta |  |
| Aurelia Sindhunirmala | @aureliasindhu |  |
| Huy Vu Bui | @vuhuybui |  |
| Juan Gavilanes | @juanseb510 |  |
| Sofia Felan | @sfelan968 |  |

## Research Questions

Our analysis will explore questions such as:

- What school characteristics are associated with differences in restrictive-practice outcomes?
- How do restrictive-practice rates vary across schools or districts?
- Are school resource levels associated with restrictive-practice patterns?
- Which resource-related variables appear most relevant to restrictive-practice outcomes?
- How can raw counts be normalized to allow fairer comparisons between schools of different sizes?
- Which variables may be useful for future predictive modeling or resource-allocation analysis?

These questions may evolve as we learn more about the available data.



# Current Milestone

### September — Data Foundation, Exploration, Preparation & Baseline Analysis

The September milestone focuses on establishing the project's data foundation and preparing the team for future modeling work.

| Task | Description | Target Date |
|---|---|---|
| **Task #1 — Define problem scope and success metrics** | Review challenge goals, identify stakeholders, define research questions, project scope, and success metrics. | Sep 15 |
| **Task #2 — Audit and organize available data** | Review datasets, document sources and variables, identify useful fields, and document data-quality issues. | Sep 15 |
| **Task #3 — Clean and preprocess data** | Handle missing values, standardize fields, investigate duplicates/outliers, and create an analysis-ready dataset. | Sep 18 |
| **Task #4 — Feature Engineering** | Create meaningful features describing school characteristics, resources, and restrictive-practice patterns. | Sep 22 |
| **Task #5 — Complete project data analysis and September findings** | Conduct EDA, investigate relationships between variables, and summarize key September findings. | Sep 29 |

Individual tasks are tracked as **GitHub Issues** and managed through our **GitHub Project board**.


# Data Analysis Workflow

Our current workflow is:

```text
Problem Definition
        ↓
Data Audit
        ↓
Data Cleaning & Preprocessing
        ↓
Feature Engineering
        ↓
EDA & Baseline Analysis
        ↓
September Findings
        ↓
Future Modeling
```
