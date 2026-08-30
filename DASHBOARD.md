# AspectVoice — Dashboard Specification

## 1. Product Dashboard Philosophy

The product should **not** expose a separate dashboard for every analytical concern.

The backend may contain independent modules for ingestion, feature discovery, aspect extraction, sentiment, severity, clustering, trend detection, scoring, and evidence retrieval. The frontend should combine these capabilities into a small number of coherent user experiences.

The recommended structure is:

```text
AspectVoice
|
+-- Product Overview
|
+-- Product Insights
|     |
|     +-- Features
|     +-- Pain Points
|     +-- Trends
|     +-- R&D Priorities
|     +-- Evidence drill-down
|
+-- Evidence Explorer
      |
      +-- Opened from an insight/detail action
```

There are therefore **two primary dashboard experiences**:

1. Product Overview
2. Product Insights

Evidence Explorer is a detail/drill-down experience rather than a separate analytical dashboard.

---

# 2. Dynamic Data Principle

The dashboards must reflect the actual data collected by the ingestion pipeline.

Vehicle identity may be configured so that the system knows what vehicle to search for. However, vehicle features must **not** be treated as a fixed hand-written ontology.

The intended analytical flow is:

```text
Vehicle selected
      |
      v
Source ingestion
      |
      v
Raw feedback
      |
      v
Cleaning + relevance filtering
      |
      v
Feature ontology discovery
      |
      v
Aspect / sentiment / severity analysis
      |
      v
Issue clustering
      |
      v
Trend + priority scoring
      |
      v
Dashboard
```

Therefore, Product Insights should display features and issues discovered from the collected feedback.

Example:

```text
Collected feedback
        |
        +--> rear-seat comfort
        +--> mirror vibration
        +--> fuel economy
        +--> display navigation
        +--> suspension
        |
        v
Discovered feature ontology
        |
        v
Product Insights
```

The UI must not imply that these features were manually entered into a static vehicle specification list.

---

# 3. Product Overview

## 3.1 Purpose

The Overview page answers:

> **How is this vehicle performing according to customer voice?**

It is intended for leadership, product managers, and users who need a fast understanding of the current state.

It should prioritize clarity over analytical depth.

---

## 3.2 Vehicle Selector

At the top of the page:

```text
Vehicle: [ Search / Select Vehicle ]
```

The selector should work from the configured vehicle identities.

The selected vehicle determines which collected and analyzed data is displayed.

It should not determine the feature ontology.

---

## 3.3 KPI Cards

Display a compact set of high-level metrics.

Recommended cards:

```text
+----------------+----------------+----------------+----------------+
| Feedback       | Overall        | Negative       | High Priority  |
| Analyzed       | Sentiment      | Feedback       | Issues         |
+----------------+----------------+----------------+----------------+
```

Potential metrics:

- Total feedback analyzed
- Positive sentiment percentage
- Neutral sentiment percentage
- Negative sentiment percentage
- Number of discovered features
- Number of recurring issues
- Number of high-priority issues
- Number of emerging issues

Do not overload the page with every backend metric.

---

## 3.4 Sentiment Trend

Show how customer sentiment changes over time.

Example:

```text
Sentiment Trend

Positive   ----/\------/\/\----
Neutral    --/\---/\/\----------
Negative   ----/---/--\/\-------
            Jan Feb Mar Apr May
```

The exact visualization can be a line or area chart.

The chart should support the selected date range.

---

## 3.5 Top Strengths

Display the most positively discussed discovered features/themes.

Example:

```text
Top Customer Strengths

1. Design
2. Performance
3. Handling
4. Braking
5. Lighting
```

These should be derived from analyzed feedback rather than manually configured.

Each item should be clickable and open the relevant Product Insights detail.

---

## 3.6 Top Pain Points

Display the most important negative or problematic themes.

Example:

```text
Top Customer Pain Points

1. Rear-seat comfort
2. Fuel economy
3. Display navigation
4. Ride comfort
5. Connectivity
```

Ranking should be driven by backend scoring rather than simple mention count alone.

---

## 3.7 Emerging Issues

Highlight issues whose activity or negative sentiment is increasing.

Example:

```text
Emerging Issues

Rear-seat comfort       Increasing
Mirror vibration        Increasing
Display navigation      Increasing
Connectivity            Increasing
```

An emerging issue should have enough evidence to avoid surfacing random one-off comments.

---

# 4. Product Insights

## 4.1 Purpose

Product Insights is the main analytical workspace.

It answers:

> **Why is the product being discussed this way, what are customers talking about, and what should the product team investigate?**

Rather than creating separate dashboards for features, pain points, trends, and R&D priorities, they should be views or filters within this single experience.

---

# 5. Feature View

## 5.1 Feature Discovery

Features displayed here must come from the discovered ontology generated after data collection and cleaning.

Example:

```text
Discovered Features

Rear-seat comfort
Fuel economy
Digital display
Braking
Suspension
Connectivity
Performance
Mirrors
Lighting
```

The list can vary by vehicle.

A feature that is not manually configured can still appear if customer feedback contains sufficient evidence for it.

---

## 5.2 Feature Summary

When a feature is selected:

```text
REAR-SEAT COMFORT

Mentions: 68
Positive: 22%
Neutral: 14%
Negative: 64%

Severity:
High       31%
Medium     49%
Low        20%

Trend:
Increasing
```

Also show:

- Number of feedback items
- Number of source groups
- Sentiment distribution
- Severity distribution
- Trend
- Related recurring issues
- Relevant use cases

---

## 5.3 Feature Evidence

A selected feature should provide a route to its underlying evidence.

For example:

```text
Rear-seat comfort

Why is this feature considered important?

68 relevant mentions
31 content items
7 source groups

Main observation:
Customers repeatedly discuss discomfort
during longer rides.

[View Evidence]
```

---

# 6. Pain Point View

The same Product Insights page should provide a ranked issue table.

Recommended columns:

| Issue | Mentions | Severity | Trend | Priority |
|---|---:|---|---|---:|
| Rear-seat comfort | 68 | High | Increasing | 86 |
| Fuel economy | 61 | High | Stable | 78 |
| Display navigation | 43 | Medium | Increasing | 64 |
| Connectivity | 31 | Medium | Increasing | 52 |

The numbers above are illustrative UI examples only. Production values must come from the backend.

---

# 7. Priority / R&D View

A user should be able to filter the Product Insights workspace to:

```text
All Issues
High Priority
Emerging
By Feature
By Severity
```

For a selected issue:

```text
REAR-SEAT COMFORT

Priority: HIGH
Score: 86/100

Mentions: 68
Source groups: 7
Trend: Increasing
Confidence: 0.87

Primary context:
Long-distance / pillion riding

Observed issue:
Recurring discomfort during extended riding.

Recommended investigation:
Investigate rear-seat ergonomics for
long-duration / pillion use.
```

The recommendation is decision support.

The dashboard must not present an AI recommendation as proof of an engineering defect.

---

# 8. Filters

Product Insights should support:

- Vehicle
- Date range
- Feature
- Issue
- Sentiment
- Severity
- Source
- Customer/use-case segment

Filters should update the analytical views without requiring separate dashboards.

---

# 9. Evidence Explorer

Evidence Explorer is a drill-down experience.

It should be opened from a feature, issue, trend, or priority item.

## 9.1 Evidence Detail

Example:

```text
REAR-SEAT COMFORT
High Priority

Why was this identified?

68 relevant mentions
31 content items
7 source groups

Trend
Jan  ███
Feb  ████
Mar  ██████
Apr  ████████

Representative feedback

"Comfort drops significantly during longer rides."

Source:
Public automotive review / video / forum

Published:
YYYY-MM-DD

[Open Source]
```

---

## 9.2 Evidence Separation

The UI should clearly distinguish three levels:

### Observed

What the customer/reviewer actually said.

### AI Interpretation

What the system inferred from multiple pieces of feedback.

### Recommendation

What a product or R&D team could investigate.

This distinction is critical for trust and auditability.

---

# 10. Competitive Intelligence

Competitive intelligence should **not** be a separate dashboard in the initial POC.

If included later, it should be a mode inside Product Insights:

```text
Product Insights

[ My Vehicle ] [ Competitor Comparison ]
```

Example:

| Feature | My Vehicle | Competitor |
|---|---|---|
| Fuel economy | Mixed | Positive |
| Ride comfort | Positive | Mixed |
| Display | Positive | Positive |
| Rear-seat comfort | Negative | Positive |

Competitive comparisons must show:

- Feedback volume
- Date range
- Source distribution
- Sentiment basis

Competitive intelligence is a Phase 2 capability and should not block the core POC.

---

# 11. Frontend Navigation

Recommended navigation:

```text
AspectVoice
|
+-- Overview
|
+-- Product Insights
|     |
|     +-- Features
|     +-- Pain Points
|     +-- Trends
|     +-- R&D Priorities
|     +-- Evidence
|
+-- Vehicle Search / Selection
```

Evidence should generally be reached through Product Insights rather than treated as a top-level analytical dashboard.

---

# 12. Backend-to-Dashboard Contract

The dashboard should consume backend outputs rather than reproduce analytical logic in the frontend.

Conceptually:

```text
Ingestion
    |
Cleaning
    |
Feature Discovery
    |
Aspect Extraction
    |
Issue Clustering
    |
Scoring
    |
API
    |
Frontend
```

The frontend should not independently calculate:

- Sentiment
- Feature discovery
- Issue severity
- Priority
- Trend classification

Those belong to the backend analytical pipeline.

---

# 13. Dynamic Feature Behavior

The dashboard must support different feature sets for different vehicles.

For example:

```text
Vehicle A
    |
    +-- Feature X
    +-- Feature Y
    +-- Feature Z

Vehicle B
    |
    +-- Feature X
    +-- Feature Q
    +-- Feature R
```

There should be no assumption that every vehicle has exactly the same feature list.

Common normalization can still exist where appropriate, but the ontology must originate from actual feedback.

---

# 14. Empty / Insufficient Data States

The dashboard must handle incomplete pipelines gracefully.

Examples:

```text
No feedback collected yet.

No feature ontology has been discovered yet.

Not enough feedback to establish a recurring issue.

Insufficient evidence to calculate a reliable trend.

Feature discovery is in progress.
```

Do not show fake zeroes or invented insights.

---

# 15. Trust and Transparency

The dashboard should make it possible to answer:

1. Where did this insight come from?
2. How many pieces of feedback support it?
3. Which sources contributed?
4. Is the issue increasing or stable?
5. What did customers actually say?
6. What part is AI interpretation?
7. What is merely a recommendation?

Every major insight should have an evidence path.

---

# 16. Visual Design Principles

The dashboard should feel like a professional product-intelligence application, not a generic analytics template.

Recommended principles:

- Clean enterprise UI
- Strong visual hierarchy
- Limited number of KPI cards
- Clear typography
- Consistent spacing
- Charts only where they answer a real question
- Tables for ranked issues
- Drill-down interactions instead of excessive navigation
- Responsive layout
- No decorative elements that distract from the analysis

Avoid creating separate cards or pages just because a backend metric exists.

---

# 17. POC Scope

For the initial POC, prioritize:

### Must Have

- Vehicle selection
- Product Overview
- Dynamic discovered feature list
- Feature-level insights
- Ranked pain points
- Sentiment trend
- Priority scoring
- Evidence drill-down
- Source attribution

### Should Have

- Emerging issue detection
- Use-case filtering
- Severity filtering
- Confidence indicators

### Phase 2

- Competitor comparison
- More source types
- Advanced segmentation
- Historical ontology evolution
- Automated recommendation tracking

---

# 18. Final UX Principle

The product should make the user journey feel like:

```text
WHAT IS HAPPENING?
        |
        v
Product Overview
        |
        v
WHAT ARE CUSTOMERS TALKING ABOUT?
        |
        v
Product Insights
        |
        v
WHAT MATTERS MOST?
        |
        v
Priority / Trend / Severity
        |
        v
WHY SHOULD I BELIEVE THIS?
        |
        v
Evidence Explorer
```

The backend remains sophisticated, but the dashboard experience stays simple.

**Two primary dashboard experiences. One evidence drill-down. Many analytical capabilities underneath.**
