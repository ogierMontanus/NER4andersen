# Repository Specification: Automated Authority Reconciliation and Entity Enrichment

## Objective

Extend the existing named-entity indexing pipeline into a multi-stage enrichment workflow capable of:

1. harvesting contextual information from editorial notes;
2. consolidating information from multiple local sources;
3. automatically reconciling entities against external authority systems;
4. supporting human validation and curation;
5. producing reusable authority data for future named-entity recognition and linking.

The repository should be designed as a practical research infrastructure component rather than as a purely experimental prototype.

---

# Existing Inputs

The repository must integrate with the current pipeline that maps source volumes against a registry of indexed names.

Current materials include:

* source texts;
* printed indexes;
* digitized index datasets;
* editorial notes;
* local authority records;
* named-entity occurrence lists;
* existing NER outputs.

The chatbot should begin by inspecting and documenting the existing codebase, data structures, transformation scripts, and intermediate outputs.

Particular attention should be paid to:

* CSV files;
* PowerQuery workflows;
* Excel sheets;
* XSLT transformations;
* AWK scripts;
* authority lookup tables;
* entity occurrence registries.

---

# Conceptual Model

For many entities two independent contextual sources exist.

## Source A: Local Entity Index

The index often contains information such as:

* profession;
* role;
* nationality;
* settlement type;
* geographic affiliation;
* explanatory labels.

Example:

| Entity | Context                  |
| ------ | ------------------------ |
| Udby   | village near Vordingborg |

---

## Source B: Editorial Notes

Editorial annotations frequently provide similar information.

Example:

> Udby, a village near Vordingborg.

or

> Winther, collector of Danish folktales.

---

# Stage 1: Consolidation

## Goal

Create a consolidated local authority layer before any external reconciliation takes place.

The chatbot should:

1. extract contextual descriptions from editorial notes;
2. extract contextual descriptions from local indexes;
3. compare the descriptions;
4. merge compatible descriptions;
5. identify inconsistencies requiring review.

The result should be a unified authority candidate record.

Example:

```json
{
  "label": "Udby",
  "entityType": "place",
  "settlementType": "village",
  "nearPlace": "Vordingborg",
  "sources": [
    "printed index",
    "editorial note"
  ]
}
```

The repository should preserve provenance for every extracted statement.

---

# Stage 2: Automated Reconciliation

## Goal

Use consolidated contextual information to improve matching against external authorities.

Target authorities include:

* Wikidata
* GND
* VIAF
* Library of Congress
* GeoNames
* national gazetteers
* project-specific authority registries

The reconciliation process should not rely solely on string matching.

Instead, contextual information should be incorporated into candidate ranking.

Example:

Input:

```json
{
  "label": "Udby",
  "entityType": "place",
  "settlementType": "village",
  "nearPlace": "Vordingborg"
}
```

Candidate ranking should consider:

* label similarity;
* alternative labels;
* entity type compatibility;
* geographic compatibility;
* temporal compatibility;
* contextual similarity.

---

## Query Construction

The repository should support enriched reconciliation queries.

Examples:

```json
{
  "name": "Udby",
  "type": "place",
  "description": "village",
  "near": "Vordingborg"
}
```

```json
{
  "name": "Winther",
  "type": "person",
  "occupation": "folklorist"
}
```

The contextual fields should influence ranking and confidence scores.

---

# Stage 3: Human Curation

Automated reconciliation must always remain reviewable.

The repository should support integration with graphical reconciliation and annotation tools.

Priority candidates include:

* OpenRefine reconciliation workflows
* OpenRefine reconciliation APIs
* Annotator-style review interfaces
* DiPublisher-based editorial workflows
* lightweight web review interfaces

Editors should be able to:

* inspect candidates;
* compare competing matches;
* approve matches;
* reject matches;
* create local authority records;
* flag uncertain cases.

---

# Repository Deliverables

## A. Data Model

Define a schema covering:

* entity labels;
* aliases;
* entity types;
* contextual descriptions;
* provenance;
* authority identifiers;
* confidence scores;
* editorial decisions.

---

## B. Extraction Pipeline

Implement modules for:

* editorial-note extraction;
* index extraction;
* contextual phrase extraction;
* provenance tracking.

---

## C. Reconciliation Layer

Implement connectors for:

* Wikidata reconciliation;
* OpenRefine-compatible reconciliation services;
* local authority services.

The architecture should allow additional authority providers to be added later.

---

## D. Curation Layer

Provide:

* reconciliation review workflows;
* approval interfaces;
* export mechanisms.

Outputs should remain compatible with:

* CSV;
* Excel;
* Wikibase-style authority models;
* future graph databases.

---

# Research Questions

The repository should explicitly evaluate:

1. How much does contextual information improve reconciliation accuracy?
2. Which contextual features contribute most to disambiguation?
3. Can editorial-note extraction improve recall in later NER workflows?
4. How closely do editorial notes and local indexes overlap?
5. Which authority systems perform best for nineteenth-century Danish cultural entities?

The system should generate reproducible evaluation reports for these questions.

---

# Success Criterion

The final repository should demonstrate that contextual information harvested from editorial notes and local indexes can be consolidated into a local authority layer and then used to achieve measurably better reconciliation results than label-only matching against external authority systems.
