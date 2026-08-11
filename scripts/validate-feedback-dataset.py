#!/usr/bin/env python3
"""Validate the DMP feedback survey dataset against DDI-CDI 1.0.

Loads data/feedback-survey-dataset.jsonld and cross-checks it against
data/feedback-survey-responses.csv, the official DDI-CDI 1.0 RDF vocabulary
(https://ddialliance.org/Specification/DDI-CDI/1.0/RDF/), and the survey's
skip-logic rules.

Checks:
 1. Valid JSON (no embedded comments) and expected top-level shape.
 2. @context declares the official DDI-CDI RDF namespace prefix.
 3. Every @type resolves to a valid DDI-CDI class IRI (or a documented tue:
    extension).
 4. Every property predicate resolves to a known IRI:
    - cdi:*  -> present in the official DDI-CDI vocabulary
    - rdfs:* -> rdfs:label / rdfs:comment
    - tue:*  -> TU/e survey extension prefix (reported as INFO, not an error)
 5. Blank-node referential integrity: every referenced id exists in the graph.
 6. DataPoint checks: exactly `respondentCount` data points with unique
    identifiers, values conform to the code lists, and the conditional
    skip-logic holds (iv4 = 2 => iv5 null; iv4 = 1 => iv5 present).
 7. ISO-8601 timestamps with startTime <= completionTime.
 8. Cross-validation against the source CSV (row count, column count,
    per-value conformance, physicalFileName).

Exit codes: 0 all pass, 1 errors, 2 usage.

Usage:
    pipenv run python scripts/validate-feedback-dataset.py
    pipenv run python scripts/validate-feedback-dataset.py <jsonld> <csv> [--offline]
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

# Official DDI-CDI 1.0 RDF namespace.
CDI_NS = "http://ddialliance.org/Specification/DDI-CDI/1.0/RDF/"
# TU/e survey extension namespace (documented local terms without a DDI-CDI home).
TUE_NS = "https://tue.nl/rescockpit/dmp-feedback/vocab/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"

# Every valid `cdi:` IRI from the official vocabulary context
# (https://ddialliance.org/Specification/DDI-CDI/1.0/RDF/ddi-cdi.jsonld).
DDI_CDI_TERMS = frozenset({
    "cdi:AccessInformation",
    "cdi:AccessInformation-copyright",
    "cdi:AccessInformation-embargo",
    "cdi:AccessInformation-license",
    "cdi:AccessInformation-rights",
    "cdi:AccessLocation",
    "cdi:AccessLocation-mimeType",
    "cdi:AccessLocation-physicalLocation",
    "cdi:AccessLocation-uri",
    "cdi:Activity",
    "cdi:Activity-definition",
    "cdi:Activity-description",
    "cdi:Activity-displayLabel",
    "cdi:Activity-entityProduced",
    "cdi:Activity-entityUsed",
    "cdi:Activity-identifier",
    "cdi:Activity-name",
    "cdi:Activity-standardModelMapping",
    "cdi:Activity_hasInternal_ControlLogic",
    "cdi:Activity_hasSubActivity_Activity",
    "cdi:Activity_has_Step",
    "cdi:Address",
    "cdi:Address-cityPlaceLocal",
    "cdi:Address-countryCode",
    "cdi:Address-effectiveDates",
    "cdi:Address-geographicPoint",
    "cdi:Address-isPreferred",
    "cdi:Address-line",
    "cdi:Address-locationName",
    "cdi:Address-postalCode",
    "cdi:Address-privacy",
    "cdi:Address-regionalCoverage",
    "cdi:Address-stateProvince",
    "cdi:Address-timeZone",
    "cdi:Address-typeOfAddress",
    "cdi:Address-typeOfLocation",
    "cdi:Agent",
    "cdi:Agent-catalogDetails",
    "cdi:Agent-identifier",
    "cdi:Agent-image",
    "cdi:Agent-purpose",
    "cdi:AgentInRole",
    "cdi:AgentInRole-agentName",
    "cdi:AgentInRole-reference",
    "cdi:AgentInRole-role",
    "cdi:AgentListing",
    "cdi:AgentListing-allowsDuplicates",
    "cdi:AgentListing-identifier",
    "cdi:AgentListing-name",
    "cdi:AgentListing-purpose",
    "cdi:AgentListing_has_Agent",
    "cdi:AgentListing_has_AgentPosition",
    "cdi:AgentListing_isDefinedBy_Concept",
    "cdi:AgentListing_isMaintainedBy_Agent",
    "cdi:AgentPosition",
    "cdi:AgentPosition-identifier",
    "cdi:AgentPosition-value",
    "cdi:AgentPosition_indexes_Agent",
    "cdi:AgentRelationship",
    "cdi:AgentRelationship-effectiveDates",
    "cdi:AgentRelationship-identifier",
    "cdi:AgentRelationship-semantics",
    "cdi:AgentRelationship_hasSource_Agent",
    "cdi:AgentRelationship_hasTarget_Agent",
    "cdi:AgentStructure",
    "cdi:AgentStructure-effectiveDates",
    "cdi:AgentStructure-identifier",
    "cdi:AgentStructure-name",
    "cdi:AgentStructure-privacy",
    "cdi:AgentStructure-purpose",
    "cdi:AgentStructure-semantics",
    "cdi:AgentStructure-specification",
    "cdi:AgentStructure-topology",
    "cdi:AgentStructure-totality",
    "cdi:AgentStructure_has_AgentRelationship",
    "cdi:AgentStructure_structures_AgentListing",
    "cdi:All",
    "cdi:AllenIntervalAlgebra",
    "cdi:AllenIntervalAlgebra-temporalIntervalRelation",
    "cdi:AndJoin",
    "cdi:AndSplit",
    "cdi:AttributeComponent",
    "cdi:AttributeComponent_qualifies_DataStructureComponent",
    "cdi:AuthorizationSource",
    "cdi:AuthorizationSource-authorizationDate",
    "cdi:AuthorizationSource-catalogDetails",
    "cdi:AuthorizationSource-identifier",
    "cdi:AuthorizationSource-legalMandate",
    "cdi:AuthorizationSource-purpose",
    "cdi:AuthorizationSource-statementOfAuthorization",
    "cdi:AuthorizationSource_has_Agent",
    "cdi:Auto",
    "cdi:BackwardChaining",
    "cdi:BibliographicName",
    "cdi:BibliographicName-affiliation",
    "cdi:Both",
    "cdi:CatalogDetails",
    "cdi:CatalogDetails-access",
    "cdi:CatalogDetails-alternativeTitle",
    "cdi:CatalogDetails-contributor",
    "cdi:CatalogDetails-creator",
    "cdi:CatalogDetails-date",
    "cdi:CatalogDetails-identifier",
    "cdi:CatalogDetails-informationSource",
    "cdi:CatalogDetails-languageOfObject",
    "cdi:CatalogDetails-provenance",
    "cdi:CatalogDetails-publisher",
    "cdi:CatalogDetails-relatedResource",
    "cdi:CatalogDetails-subTitle",
    "cdi:CatalogDetails-summary",
    "cdi:CatalogDetails-title",
    "cdi:CatalogDetails-typeOfResource",
    "cdi:Category",
    "cdi:Category-descriptiveText",
    "cdi:CategoryPosition",
    "cdi:CategoryPosition-identifier",
    "cdi:CategoryPosition-value",
    "cdi:CategoryPosition_indexes_Category",
    "cdi:CategoryRelationStructure",
    "cdi:CategoryRelationStructure-identifier",
    "cdi:CategoryRelationStructure-name",
    "cdi:CategoryRelationStructure-purpose",
    "cdi:CategoryRelationStructure-semantics",
    "cdi:CategoryRelationStructure-specification",
    "cdi:CategoryRelationStructure-topology",
    "cdi:CategoryRelationStructure-totality",
    "cdi:CategoryRelationStructure_has_CategoryRelationship",
    "cdi:CategoryRelationStructure_structures_CategorySet",
    "cdi:CategoryRelationship",
    "cdi:CategoryRelationship-identifier",
    "cdi:CategoryRelationship-semantics",
    "cdi:CategoryRelationship_hasSource_Category",
    "cdi:CategoryRelationship_hasTarget_Category",
    "cdi:CategorySet",
    "cdi:CategorySet_has_Category",
    "cdi:CategorySet_has_CategoryPosition",
    "cdi:CategoryStatistic",
    "cdi:CategoryStatistic-identifier",
    "cdi:CategoryStatistic-statistic",
    "cdi:CategoryStatistic-typeOfCategoryStatistic",
    "cdi:CategoryStatistic_appliesTo_InstanceVariable",
    "cdi:CategoryStatistic_for_Category",
    "cdi:ClassificationFamily",
    "cdi:ClassificationFamily-catalogDetails",
    "cdi:ClassificationFamily-identifier",
    "cdi:ClassificationFamily-name",
    "cdi:ClassificationFamily-purpose",
    "cdi:ClassificationFamily_groups_ClassificationSeries",
    "cdi:ClassificationFamily_isDefinedBy_Concept",
    "cdi:ClassificationFamily_uses_ClassificationIndex",
    "cdi:ClassificationIndex",
    "cdi:ClassificationIndex-allowsDuplicates",
    "cdi:ClassificationIndex-availableLanguage",
    "cdi:ClassificationIndex-catalogDetails",
    "cdi:ClassificationIndex-codingInstruction",
    "cdi:ClassificationIndex-corrections",
    "cdi:ClassificationIndex-identifier",
    "cdi:ClassificationIndex-name",
    "cdi:ClassificationIndex-purpose",
    "cdi:ClassificationIndex-releaseDate",
    "cdi:ClassificationIndexEntry",
    "cdi:ClassificationIndexEntry-catalogDetails",
    "cdi:ClassificationIndexEntry-codingInstruction",
    "cdi:ClassificationIndexEntry-entry",
    "cdi:ClassificationIndexEntry-identifier",
    "cdi:ClassificationIndexEntry-validDates",
    "cdi:ClassificationIndexEntryPosition",
    "cdi:ClassificationIndexEntryPosition-identifier",
    "cdi:ClassificationIndexEntryPosition-value",
    "cdi:ClassificationIndexEntryPosition_indexes_ClassificationIndexEntry",
    "cdi:ClassificationIndex_hasContact_Agent",
    "cdi:ClassificationIndex_has_ClassificationIndexEntry",
    "cdi:ClassificationIndex_has_ClassificationIndexEntryPosition",
    "cdi:ClassificationIndex_isDefinedBy_Concept",
    "cdi:ClassificationIndex_isMaintainedBy_Agent",
    "cdi:ClassificationItem",
    "cdi:ClassificationItem-changeFromPreviousVersion",
    "cdi:ClassificationItem-changeLog",
    "cdi:ClassificationItem-explanatoryNotes",
    "cdi:ClassificationItem-futureNotes",
    "cdi:ClassificationItem-identifier",
    "cdi:ClassificationItem-isGenerated",
    "cdi:ClassificationItem-isValid",
    "cdi:ClassificationItem-name",
    "cdi:ClassificationItem-validDates",
    "cdi:ClassificationItemPosition",
    "cdi:ClassificationItemPosition-identifier",
    "cdi:ClassificationItemPosition-value",
    "cdi:ClassificationItemPosition_indexes_ClassificationItem",
    "cdi:ClassificationItemRelationship",
    "cdi:ClassificationItemRelationship-identifier",
    "cdi:ClassificationItemRelationship-semantics",
    "cdi:ClassificationItemRelationship_hasSource_ClassificationItem",
    "cdi:ClassificationItemRelationship_hasTarget_ClassificationItem",
    "cdi:ClassificationItemStructure",
    "cdi:ClassificationItemStructure-displayLabel",
    "cdi:ClassificationItemStructure-identifier",
    "cdi:ClassificationItemStructure-name",
    "cdi:ClassificationItemStructure-purpose",
    "cdi:ClassificationItemStructure-semantics",
    "cdi:ClassificationItemStructure-specification",
    "cdi:ClassificationItemStructure-topology",
    "cdi:ClassificationItemStructure-totality",
    "cdi:ClassificationItemStructure_has_ClassificationItemRelationship",
    "cdi:ClassificationItemStructure_structures_StatisticalClassification",
    "cdi:ClassificationItem_denotes_Category",
    "cdi:ClassificationItem_excludes_ClassificationItem",
    "cdi:ClassificationItem_hasRulingBy_AuthorizationSource",
    "cdi:ClassificationItem_uses_Notation",
    "cdi:ClassificationPosition",
    "cdi:ClassificationPosition-identifier",
    "cdi:ClassificationPosition-value",
    "cdi:ClassificationPosition_indexes_StatisticalClassification",
    "cdi:ClassificationSeries",
    "cdi:ClassificationSeries-allowsDuplicates",
    "cdi:ClassificationSeries-catalogDetails",
    "cdi:ClassificationSeries-context",
    "cdi:ClassificationSeries-identifier",
    "cdi:ClassificationSeries-keyword",
    "cdi:ClassificationSeries-name",
    "cdi:ClassificationSeries-objectsOrUnitsClassified",
    "cdi:ClassificationSeries-purpose",
    "cdi:ClassificationSeries-subject",
    "cdi:ClassificationSeriesStructure",
    "cdi:ClassificationSeriesStructure-identifier",
    "cdi:ClassificationSeriesStructure-name",
    "cdi:ClassificationSeriesStructure-purpose",
    "cdi:ClassificationSeriesStructure-semantics",
    "cdi:ClassificationSeriesStructure-specification",
    "cdi:ClassificationSeriesStructure-topology",
    "cdi:ClassificationSeriesStructure-totality",
    "cdi:ClassificationSeriesStructure_has_StatisticalClassificationRelationship",
    "cdi:ClassificationSeriesStructure_structures_ClassificationSeries",
    "cdi:ClassificationSeries_has_ClassificationPosition",
    "cdi:ClassificationSeries_has_StatisticalClassification",
    "cdi:ClassificationSeries_isDefinedBy_Concept",
    "cdi:ClassificationSeries_isOwnedBy_Agent",
    "cdi:CloseMatch",
    "cdi:Code",
    "cdi:Code-identifier",
    "cdi:CodeList",
    "cdi:CodeList-allowsDuplicates",
    "cdi:CodeListStructure",
    "cdi:CodeListStructure-identifier",
    "cdi:CodeListStructure-name",
    "cdi:CodeListStructure-purpose",
    "cdi:CodeListStructure-semantics",
    "cdi:CodeListStructure-specification",
    "cdi:CodeListStructure-topology",
    "cdi:CodeListStructure-totality",
    "cdi:CodeListStructure_has_CodeRelationship",
    "cdi:CodeListStructure_structures_CodeList",
    "cdi:CodeList_has_Code",
    "cdi:CodeList_has_CodePosition",
    "cdi:CodePosition",
    "cdi:CodePosition-identifier",
    "cdi:CodePosition-value",
    "cdi:CodePosition_indexes_Code",
    "cdi:CodeRelationship",
    "cdi:CodeRelationship-identifier",
    "cdi:CodeRelationship-semantics",
    "cdi:CodeRelationship_hasSource_Code",
    "cdi:CodeRelationship_hasTarget_Code",
    "cdi:Code_denotes_Category",
    "cdi:Code_uses_Notation",
    "cdi:Collapse",
    "cdi:CombinedDate",
    "cdi:CombinedDate-isoDate",
    "cdi:CombinedDate-nonIsoDate",
    "cdi:CombinedDate-semantics",
    "cdi:Command",
    "cdi:Command-commandContent",
    "cdi:Command-programLanguage",
    "cdi:CommandCode",
    "cdi:CommandCode-command",
    "cdi:CommandCode-commandFile",
    "cdi:CommandCode-description",
    "cdi:CommandFile",
    "cdi:CommandFile-location",
    "cdi:CommandFile-uri",
    "cdi:ComponentPosition",
    "cdi:ComponentPosition-identifier",
    "cdi:ComponentPosition-value",
    "cdi:ComponentPosition_indexes_DataStructureComponent",
    "cdi:Concept",
    "cdi:Concept-catalogDetails",
    "cdi:Concept-definition",
    "cdi:Concept-displayLabel",
    "cdi:Concept-externalDefinition",
    "cdi:Concept-identifier",
    "cdi:Concept-name",
    "cdi:ConceptMap",
    "cdi:ConceptMap-correspondence",
    "cdi:ConceptMap-displayLabel",
    "cdi:ConceptMap-identifier",
    "cdi:ConceptMap-usage",
    "cdi:ConceptMap-validDates",
    "cdi:ConceptMap_hasSource_Concept",
    "cdi:ConceptMap_hasTarget_Concept",
    "cdi:ConceptRelationship",
    "cdi:ConceptRelationship-identifier",
    "cdi:ConceptRelationship-semantics",
    "cdi:ConceptRelationship_hasSource_Concept",
    "cdi:ConceptRelationship_hasTarget_Concept",
    "cdi:ConceptStructure",
    "cdi:ConceptStructure-identifier",
    "cdi:ConceptStructure-name",
    "cdi:ConceptStructure-purpose",
    "cdi:ConceptStructure-semantics",
    "cdi:ConceptStructure-specification",
    "cdi:ConceptStructure-topology",
    "cdi:ConceptStructure-totality",
    "cdi:ConceptStructure_has_ConceptRelationship",
    "cdi:ConceptStructure_structures_ConceptSystem",
    "cdi:ConceptSystem",
    "cdi:ConceptSystem-allowsDuplicates",
    "cdi:ConceptSystem-catalogDetails",
    "cdi:ConceptSystem-externalDefinition",
    "cdi:ConceptSystem-identifier",
    "cdi:ConceptSystem-name",
    "cdi:ConceptSystem-purpose",
    "cdi:ConceptSystemCorrespondence",
    "cdi:ConceptSystemCorrespondence-catalogDetails",
    "cdi:ConceptSystemCorrespondence-displayLabel",
    "cdi:ConceptSystemCorrespondence-identifier",
    "cdi:ConceptSystemCorrespondence-purpose",
    "cdi:ConceptSystemCorrespondence-usage",
    "cdi:ConceptSystemCorrespondence_has_ConceptMap",
    "cdi:ConceptSystemCorrespondence_maps_ConceptSystem",
    "cdi:ConceptSystem_has_Concept",
    "cdi:ConceptSystem_isDefinedBy_Concept",
    "cdi:Concept_uses_Concept",
    "cdi:ConceptualDomain",
    "cdi:ConceptualDomain-catalogDetails",
    "cdi:ConceptualDomain-displayLabel",
    "cdi:ConceptualDomain-identifier",
    "cdi:ConceptualDomain_isDescribedBy_ValueAndConceptDescription",
    "cdi:ConceptualDomain_takesConceptsFrom_ConceptSystem",
    "cdi:ConceptualValue",
    "cdi:ConceptualValue_hasConceptFrom_ConceptualDomain",
    "cdi:ConceptualVariable",
    "cdi:ConceptualVariable-descriptiveText",
    "cdi:ConceptualVariable-unitOfMeasureKind",
    "cdi:ConceptualVariable_measures_UnitType",
    "cdi:ConceptualVariable_takesSentinelConceptsFrom_SentinelConceptualDomain",
    "cdi:ConceptualVariable_takesSubstantiveConceptsFrom_SubstantiveConceptualDomain",
    "cdi:ConditionalControlLogic",
    "cdi:ConditionalControlLogic-condition",
    "cdi:ConditionalControlLogic-construct",
    "cdi:ContactInformation",
    "cdi:ContactInformation-address",
    "cdi:ContactInformation-email",
    "cdi:ContactInformation-emessaging",
    "cdi:ContactInformation-telephone",
    "cdi:ContactInformation-website",
    "cdi:Contains",
    "cdi:Continuous",
    "cdi:ControlLogic",
    "cdi:ControlLogic-description",
    "cdi:ControlLogic-displayLabel",
    "cdi:ControlLogic-identifier",
    "cdi:ControlLogic-name",
    "cdi:ControlLogic-workflow",
    "cdi:ControlLogic_hasSubControlLogic_ControlLogic",
    "cdi:ControlLogic_has_InformationFlowDefinition",
    "cdi:ControlLogic_informs_ProcessingAgent",
    "cdi:ControlLogic_invokes_Activity",
    "cdi:ControlledVocabularyEntry",
    "cdi:ControlledVocabularyEntry-entryReference",
    "cdi:ControlledVocabularyEntry-entryValue",
    "cdi:ControlledVocabularyEntry-name",
    "cdi:ControlledVocabularyEntry-valueForOther",
    "cdi:ControlledVocabularyEntry-vocabulary",
    "cdi:CorrespondenceDefinition",
    "cdi:CorrespondenceDefinition-commonality",
    "cdi:CorrespondenceDefinition-commonalityCode",
    "cdi:CorrespondenceDefinition-difference",
    "cdi:CorrespondenceDefinition-matching",
    "cdi:CorrespondenceTable",
    "cdi:CorrespondenceTable-catalogDetails",
    "cdi:CorrespondenceTable-effectiveDates",
    "cdi:CorrespondenceTable-identifier",
    "cdi:CorrespondenceTable_hasContact_Agent",
    "cdi:CorrespondenceTable_hasSource_Level",
    "cdi:CorrespondenceTable_hasTarget_Level",
    "cdi:CorrespondenceTable_has_ConceptMap",
    "cdi:CorrespondenceTable_isMaintainedBy_Agent",
    "cdi:CorrespondenceTable_isOwnedBy_Agent",
    "cdi:CorrespondenceTable_mapsTo_StatisticalClassification",
    "cdi:Curator",
    "cdi:DataPoint",
    "cdi:DataPoint-catalogDetails",
    "cdi:DataPoint-identifier",
    "cdi:DataPointPosition",
    "cdi:DataPointPosition-identifier",
    "cdi:DataPointPosition-value",
    "cdi:DataPointPosition_indexes_DataPoint",
    "cdi:DataPointRelationship",
    "cdi:DataPointRelationship-identifier",
    "cdi:DataPointRelationship-semantics",
    "cdi:DataPointRelationship_hasSource_DataPoint",
    "cdi:DataPointRelationship_hasTarget_DataPoint",
    "cdi:DataPoint_correspondsTo_DataStructureComponent",
    "cdi:DataPoint_isDescribedBy_InstanceVariable",
    "cdi:DataSet",
    "cdi:DataSet-catalogDetails",
    "cdi:DataSet-identifier",
    "cdi:DataSet_has_DataPoint",
    "cdi:DataSet_has_Key",
    "cdi:DataSet_isStructuredBy_DataStructure",
    "cdi:DataStore",
    "cdi:DataStore-aboutMissing",
    "cdi:DataStore-allowsDuplicates",
    "cdi:DataStore-catalogDetails",
    "cdi:DataStore-characterSet",
    "cdi:DataStore-dataStoreType",
    "cdi:DataStore-identifier",
    "cdi:DataStore-name",
    "cdi:DataStore-purpose",
    "cdi:DataStore-recordCount",
    "cdi:DataStore_has_LogicalRecord",
    "cdi:DataStore_has_LogicalRecordPosition",
    "cdi:DataStore_has_RecordRelation",
    "cdi:DataStore_isDefinedBy_Concept",
    "cdi:DataStructure",
    "cdi:DataStructureComponent",
    "cdi:DataStructureComponent-identifier",
    "cdi:DataStructureComponent-semantic",
    "cdi:DataStructureComponent-specialization",
    "cdi:DataStructureComponent_isDefinedBy_RepresentedVariable",
    "cdi:DataStructure_has_ComponentPosition",
    "cdi:DataStructure_has_DataStructureComponent",
    "cdi:DataStructure_has_ForeignKey",
    "cdi:DataStructure_has_PrimaryKey",
    "cdi:DateRange",
    "cdi:DateRange-endDate",
    "cdi:DateRange-startDate",
    "cdi:Datum",
    "cdi:Datum-catalogDetails",
    "cdi:Datum-identifier",
    "cdi:Datum_denotes_ConceptualValue",
    "cdi:Datum_isBoundedBy_InstanceVariable",
    "cdi:Datum_uses_InstanceValue",
    "cdi:Datum_uses_Notation",
    "cdi:DecimalDegree",
    "cdi:DecimalMinutes",
    "cdi:DegreesMinutesSeconds",
    "cdi:Descriptor",
    "cdi:DescriptorValueDomain",
    "cdi:DescriptorVariable",
    "cdi:DescriptorVariable_takesSubstantiveValuesFrom_DescriptorValueDomain",
    "cdi:Descriptor_hasValueFrom_DescriptorValueDomain",
    "cdi:Descriptor_identifies_ReferenceVariable",
    "cdi:Descriptor_refersTo_ReferenceValue",
    "cdi:DeterministicImperative",
    "cdi:DimensionComponent",
    "cdi:DimensionComponent-categoricalAdditivity",
    "cdi:DimensionComponent_isStructuredBy_ValueDomain",
    "cdi:DimensionGroup",
    "cdi:DimensionGroup-identifier",
    "cdi:DimensionGroup-name",
    "cdi:DimensionGroup_has_DimensionComponent",
    "cdi:DimensionalDataSet",
    "cdi:DimensionalDataSet-name",
    "cdi:DimensionalDataSet_represents_ScopedMeasure",
    "cdi:DimensionalDataStructure",
    "cdi:DimensionalDataStructure_uses_DimensionGroup",
    "cdi:DimensionalKey",
    "cdi:DimensionalKeyDefinition",
    "cdi:DimensionalKeyDefinitionMember",
    "cdi:DimensionalKeyDefinitionMember_isRepresentedBy_DimensionalKeyMember",
    "cdi:DimensionalKeyMember",
    "cdi:DimensionalKeyMember_hasValueFrom_CodeList",
    "cdi:Disjoint",
    "cdi:ElectronicMessageSystem",
    "cdi:ElectronicMessageSystem-contactAddress",
    "cdi:ElectronicMessageSystem-effectiveDates",
    "cdi:ElectronicMessageSystem-isPreferred",
    "cdi:ElectronicMessageSystem-privacy",
    "cdi:ElectronicMessageSystem-typeOfService",
    "cdi:Else",
    "cdi:Email",
    "cdi:Email-effectiveDates",
    "cdi:Email-internetEmail",
    "cdi:Email-isPreferred",
    "cdi:Email-privacy",
    "cdi:Email-typeOfEmail",
    "cdi:EmbargoInformation",
    "cdi:EmbargoInformation-description",
    "cdi:EmbargoInformation-period",
    "cdi:End",
    "cdi:EnumerationDomain",
    "cdi:EnumerationDomain-identifier",
    "cdi:EnumerationDomain-name",
    "cdi:EnumerationDomain-purpose",
    "cdi:EnumerationDomain_isDefinedBy_Concept",
    "cdi:EnumerationDomain_references_CategorySet",
    "cdi:EnumerationDomain_uses_LevelStructure",
    "cdi:Equal",
    "cdi:Equals",
    "cdi:ExactMatch",
    "cdi:Feet",
    "cdi:Feminine",
    "cdi:Finishes",
    "cdi:ForeignKey",
    "cdi:ForeignKey-identifier",
    "cdi:ForeignKeyComponent",
    "cdi:ForeignKeyComponent-identifier",
    "cdi:ForeignKeyComponent_correspondsTo_DataStructureComponent",
    "cdi:ForeignKeyComponent_references_PrimaryKeyComponent",
    "cdi:ForeignKey_isComposedOf_ForeignKeyComponent",
    "cdi:ForwardChaining",
    "cdi:FundingInformation",
    "cdi:FundingInformation-fundingAgent",
    "cdi:FundingInformation-grantNumber",
    "cdi:GenderNeutral",
    "cdi:GeoRole",
    "cdi:GeoRole-geography",
    "cdi:GreaterThan",
    "cdi:GreaterThanOrEqualTo",
    "cdi:Identifier",
    "cdi:Identifier-ddiIdentifier",
    "cdi:Identifier-isDdiIdentifierPersistent",
    "cdi:Identifier-isDdiIdentifierUniversallyUnique",
    "cdi:Identifier-nonDdiIdentifier",
    "cdi:Identifier-uri",
    "cdi:Identifier-versionDate",
    "cdi:Identifier-versionRationale",
    "cdi:Identifier-versionResponsibility",
    "cdi:IdentifierComponent",
    "cdi:IfThen",
    "cdi:Individual",
    "cdi:Individual-contactInformation",
    "cdi:Individual-individualName",
    "cdi:IndividualName",
    "cdi:IndividualName-abbreviation",
    "cdi:IndividualName-context",
    "cdi:IndividualName-effectiveDates",
    "cdi:IndividualName-firstGiven",
    "cdi:IndividualName-fullName",
    "cdi:IndividualName-isFormal",
    "cdi:IndividualName-isPreferred",
    "cdi:IndividualName-lastFamily",
    "cdi:IndividualName-middle",
    "cdi:IndividualName-prefix",
    "cdi:IndividualName-sex",
    "cdi:IndividualName-suffix",
    "cdi:IndividualName-typeOfIndividualName",
    "cdi:InformationFlowDefinition",
    "cdi:InformationFlowDefinition-identifier",
    "cdi:InformationFlowDefinition_from_Parameter",
    "cdi:InformationFlowDefinition_to_Parameter",
    "cdi:Inherit",
    "cdi:InstanceKey",
    "cdi:InstanceKey_has_InstanceValue",
    "cdi:InstanceKey_refersTo_ReferenceValue",
    "cdi:InstanceValue",
    "cdi:InstanceValue-content",
    "cdi:InstanceValue-identifier",
    "cdi:InstanceValue-whiteSpace",
    "cdi:InstanceValue_hasValueFrom_ValueDomain",
    "cdi:InstanceValue_isStoredIn_DataPoint",
    "cdi:InstanceValue_represents_ConceptualValue",
    "cdi:InstanceVariable",
    "cdi:InstanceVariable-physicalDataType",
    "cdi:InstanceVariable-platformType",
    "cdi:InstanceVariable-source",
    "cdi:InstanceVariable-variableFunction",
    "cdi:InstanceVariableMap",
    "cdi:InstanceVariableMap-comparison",
    "cdi:InstanceVariableMap-correspondence",
    "cdi:InstanceVariableMap-identifier",
    "cdi:InstanceVariableMap-setValue",
    "cdi:InstanceVariableMap_hasSource_InstanceVariable",
    "cdi:InstanceVariableMap_hasTarget_InstanceVariable",
    "cdi:InstanceVariable_has_PhysicalSegmentLayout",
    "cdi:InstanceVariable_has_ValueMapping",
    "cdi:InternationalIdentifier",
    "cdi:InternationalIdentifier-identifierContent",
    "cdi:InternationalIdentifier-isURI",
    "cdi:InternationalIdentifier-managingAgency",
    "cdi:InternationalRegistrationDataIdentifier",
    "cdi:InternationalRegistrationDataIdentifier-dataIdentifier",
    "cdi:InternationalRegistrationDataIdentifier-registrationAuthorityIdentifier",
    "cdi:InternationalRegistrationDataIdentifier-versionIdentifier",
    "cdi:InternationalString",
    "cdi:InternationalString-languageSpecificString",
    "cdi:Interval",
    "cdi:Key",
    "cdi:Key-identifier",
    "cdi:KeyDefinition",
    "cdi:KeyDefinition-identifier",
    "cdi:KeyDefinitionMember",
    "cdi:KeyDefinition_correspondsTo_Unit",
    "cdi:KeyDefinition_correspondsTo_Universe",
    "cdi:KeyDefinition_has_KeyDefinitionMember",
    "cdi:KeyMember",
    "cdi:KeyMember_isBasedOn_DataStructureComponent",
    "cdi:KeyValueDataStore",
    "cdi:KeyValueStructure",
    "cdi:Key_correspondsTo_Unit",
    "cdi:Key_correspondsTo_Universe",
    "cdi:Key_has_KeyMember",
    "cdi:Key_identifies_DataPoint",
    "cdi:Key_represents_KeyDefinition",
    "cdi:LabelForDisplay",
    "cdi:LabelForDisplay-locationVariant",
    "cdi:LabelForDisplay-maxLength",
    "cdi:LabelForDisplay-validDates",
    "cdi:LanguageString",
    "cdi:LanguageString-content",
    "cdi:LanguageString-isTranslatable",
    "cdi:LanguageString-isTranslated",
    "cdi:LanguageString-language",
    "cdi:LanguageString-scope",
    "cdi:LanguageString-structureUsed",
    "cdi:LanguageString-translationDate",
    "cdi:LanguageString-translationSourceLanguage",
    "cdi:LessThan",
    "cdi:LessThanOrEqualTo",
    "cdi:Level",
    "cdi:Level-displayLabel",
    "cdi:Level-identifier",
    "cdi:Level-levelNumber",
    "cdi:LevelStructure",
    "cdi:LevelStructure-catalogDetails",
    "cdi:LevelStructure-identifier",
    "cdi:LevelStructure-name",
    "cdi:LevelStructure-usage",
    "cdi:LevelStructure-validDateRange",
    "cdi:LevelStructure_has_Level",
    "cdi:Level_groups_ClassificationItem",
    "cdi:Level_isDefinedBy_Concept",
    "cdi:LicenseInformation",
    "cdi:LicenseInformation-contact",
    "cdi:LicenseInformation-description",
    "cdi:LicenseInformation-licenseAgent",
    "cdi:LicenseInformation-licenseReference",
    "cdi:LogicalRecord",
    "cdi:LogicalRecord-identifier",
    "cdi:LogicalRecordPosition",
    "cdi:LogicalRecordPosition-identifier",
    "cdi:LogicalRecordPosition-value",
    "cdi:LogicalRecordPosition_indexes_LogicalRecord",
    "cdi:LogicalRecordRelationStructure",
    "cdi:LogicalRecordRelationStructure-identifier",
    "cdi:LogicalRecordRelationStructure-name",
    "cdi:LogicalRecordRelationStructure-purpose",
    "cdi:LogicalRecordRelationStructure-semantics",
    "cdi:LogicalRecordRelationStructure-specification",
    "cdi:LogicalRecordRelationStructure-topology",
    "cdi:LogicalRecordRelationStructure-totality",
    "cdi:LogicalRecordRelationStructure_has_LogicalRecordRelationship",
    "cdi:LogicalRecordRelationStructure_structures_DataStore",
    "cdi:LogicalRecordRelationship",
    "cdi:LogicalRecordRelationship-identifier",
    "cdi:LogicalRecordRelationship-semantics",
    "cdi:LogicalRecordRelationship_hasSource_LogicalRecord",
    "cdi:LogicalRecordRelationship_hasTarget_LogicalRecord",
    "cdi:LogicalRecord_has_InstanceVariable",
    "cdi:LogicalRecord_isDefinedBy_Concept",
    "cdi:LogicalRecord_organizes_DataSet",
    "cdi:LongDataSet",
    "cdi:LongDataStructure",
    "cdi:LongKey",
    "cdi:LongMainKeyMember",
    "cdi:Loop",
    "cdi:Ltr",
    "cdi:Machine",
    "cdi:Machine-accessLocation",
    "cdi:Machine-function",
    "cdi:Machine-machineInterface",
    "cdi:Machine-name",
    "cdi:Machine-ownerOperatorContact",
    "cdi:Machine-typeOfMachine",
    "cdi:MainKeyMember",
    "cdi:MainKeyMember_hasValueFrom_SubstantiveValueDomain",
    "cdi:Masculine",
    "cdi:MeasureComponent",
    "cdi:MeasureComponent-name",
    "cdi:Meets",
    "cdi:Meters",
    "cdi:MissingOnly",
    "cdi:ModelIdentification",
    "cdi:ModelIdentification-acronym",
    "cdi:ModelIdentification-language",
    "cdi:ModelIdentification-majorVersion",
    "cdi:ModelIdentification-minorVersion",
    "cdi:ModelIdentification-subtitle",
    "cdi:ModelIdentification-title",
    "cdi:ModelIdentification-uri",
    "cdi:Neither",
    "cdi:Nominal",
    "cdi:NonDdiIdentifier",
    "cdi:NonDdiIdentifier-managingAgency",
    "cdi:NonDdiIdentifier-type",
    "cdi:NonDdiIdentifier-value",
    "cdi:NonDdiIdentifier-version",
    "cdi:NonDeterministicDeclarative",
    "cdi:NonIsoDate",
    "cdi:NonIsoDate-calendar",
    "cdi:NonIsoDate-dateContent",
    "cdi:NonIsoDate-nonIsoDateFormat",
    "cdi:None",
    "cdi:NotEqual",
    "cdi:Notation",
    "cdi:Notation-content",
    "cdi:Notation-identifier",
    "cdi:Notation-whiteSpace",
    "cdi:Notation_represents_Category",
    "cdi:ObjectAttributeSelector",
    "cdi:ObjectAttributeSelector-refinedBy",
    "cdi:ObjectAttributeSelector-refinedByOrderNumber",
    "cdi:ObjectAttributeSelector-value",
    "cdi:ObjectName",
    "cdi:ObjectName-context",
    "cdi:ObjectName-name",
    "cdi:Ordinal",
    "cdi:Organization",
    "cdi:Organization-contactInformation",
    "cdi:Organization-organizationName",
    "cdi:OrganizationName",
    "cdi:OrganizationName-abbreviation",
    "cdi:OrganizationName-effectiveDates",
    "cdi:OrganizationName-isFormal",
    "cdi:OrganizationName-typeOfOrganizationName",
    "cdi:Overlaps",
    "cdi:PairedControlledVocabularyEntry",
    "cdi:PairedControlledVocabularyEntry-extent",
    "cdi:PairedControlledVocabularyEntry-term",
    "cdi:Parameter",
    "cdi:Parameter-entityBound",
    "cdi:Parameter-identifier",
    "cdi:Parameter-name",
    "cdi:Partial",
    "cdi:PhysicalDataSet",
    "cdi:PhysicalDataSet-allowsDuplicates",
    "cdi:PhysicalDataSet-catalogDetails",
    "cdi:PhysicalDataSet-identifier",
    "cdi:PhysicalDataSet-name",
    "cdi:PhysicalDataSet-numberOfSegments",
    "cdi:PhysicalDataSet-overview",
    "cdi:PhysicalDataSet-physicalFileName",
    "cdi:PhysicalDataSet-purpose",
    "cdi:PhysicalDataSetStructure",
    "cdi:PhysicalDataSetStructure-identifier",
    "cdi:PhysicalDataSetStructure-name",
    "cdi:PhysicalDataSetStructure-purpose",
    "cdi:PhysicalDataSetStructure-semantics",
    "cdi:PhysicalDataSetStructure-specification",
    "cdi:PhysicalDataSetStructure-topology",
    "cdi:PhysicalDataSetStructure-totality",
    "cdi:PhysicalDataSetStructure_correspondsTo_DataStructure",
    "cdi:PhysicalDataSetStructure_has_PhysicalRecordSegmentRelationship",
    "cdi:PhysicalDataSetStructure_structures_PhysicalDataSet",
    "cdi:PhysicalDataSet_correspondsTo_DataSet",
    "cdi:PhysicalDataSet_formats_DataStore",
    "cdi:PhysicalDataSet_has_InstanceVariable",
    "cdi:PhysicalDataSet_has_PhysicalRecordSegment",
    "cdi:PhysicalDataSet_has_PhysicalRecordSegmentPosition",
    "cdi:PhysicalDataSet_isDefinedBy_Concept",
    "cdi:PhysicalLayoutRelationStructure",
    "cdi:PhysicalLayoutRelationStructure-criteria",
    "cdi:PhysicalLayoutRelationStructure-identifier",
    "cdi:PhysicalLayoutRelationStructure-name",
    "cdi:PhysicalLayoutRelationStructure-purpose",
    "cdi:PhysicalLayoutRelationStructure-semantics",
    "cdi:PhysicalLayoutRelationStructure-specification",
    "cdi:PhysicalLayoutRelationStructure-topology",
    "cdi:PhysicalLayoutRelationStructure-totality",
    "cdi:PhysicalLayoutRelationStructure_has_ValueMappingRelationship",
    "cdi:PhysicalLayoutRelationStructure_structures_PhysicalSegmentLayout",
    "cdi:PhysicalRecordSegment",
    "cdi:PhysicalRecordSegment-catalogDetails",
    "cdi:PhysicalRecordSegment-identifier",
    "cdi:PhysicalRecordSegment-name",
    "cdi:PhysicalRecordSegment-physicalFileName",
    "cdi:PhysicalRecordSegment-purpose",
    "cdi:PhysicalRecordSegmentPosition",
    "cdi:PhysicalRecordSegmentPosition-identifier",
    "cdi:PhysicalRecordSegmentPosition-value",
    "cdi:PhysicalRecordSegmentPosition_indexes_PhysicalRecordSegment",
    "cdi:PhysicalRecordSegmentRelationship",
    "cdi:PhysicalRecordSegmentRelationship-identifier",
    "cdi:PhysicalRecordSegmentRelationship-semantics",
    "cdi:PhysicalRecordSegmentRelationship_hasSource_PhysicalRecordSegment",
    "cdi:PhysicalRecordSegmentRelationship_hasTarget_PhysicalRecordSegment",
    "cdi:PhysicalRecordSegmentStructure",
    "cdi:PhysicalRecordSegmentStructure-identifier",
    "cdi:PhysicalRecordSegmentStructure-name",
    "cdi:PhysicalRecordSegmentStructure-purpose",
    "cdi:PhysicalRecordSegmentStructure-semantics",
    "cdi:PhysicalRecordSegmentStructure-specification",
    "cdi:PhysicalRecordSegmentStructure-topology",
    "cdi:PhysicalRecordSegmentStructure-totality",
    "cdi:PhysicalRecordSegmentStructure_has_DataPointRelationship",
    "cdi:PhysicalRecordSegmentStructure_structures_PhysicalRecordSegment",
    "cdi:PhysicalRecordSegment_has_DataPoint",
    "cdi:PhysicalRecordSegment_has_DataPointPosition",
    "cdi:PhysicalRecordSegment_has_PhysicalSegmentLayout",
    "cdi:PhysicalRecordSegment_isDefinedBy_Concept",
    "cdi:PhysicalRecordSegment_mapsTo_LogicalRecord",
    "cdi:PhysicalRecordSegment_represents_Population",
    "cdi:PhysicalSegmentLayout",
    "cdi:PhysicalSegmentLayout-allowsDuplicates",
    "cdi:PhysicalSegmentLayout-arrayBase",
    "cdi:PhysicalSegmentLayout-catalogDetails",
    "cdi:PhysicalSegmentLayout-commentPrefix",
    "cdi:PhysicalSegmentLayout-delimiter",
    "cdi:PhysicalSegmentLayout-encoding",
    "cdi:PhysicalSegmentLayout-escapeCharacter",
    "cdi:PhysicalSegmentLayout-hasHeader",
    "cdi:PhysicalSegmentLayout-headerIsCaseSensitive",
    "cdi:PhysicalSegmentLayout-headerRowCount",
    "cdi:PhysicalSegmentLayout-identifier",
    "cdi:PhysicalSegmentLayout-isDelimited",
    "cdi:PhysicalSegmentLayout-isFixedWidth",
    "cdi:PhysicalSegmentLayout-lineTerminator",
    "cdi:PhysicalSegmentLayout-name",
    "cdi:PhysicalSegmentLayout-nullSequence",
    "cdi:PhysicalSegmentLayout-overview",
    "cdi:PhysicalSegmentLayout-purpose",
    "cdi:PhysicalSegmentLayout-quoteCharacter",
    "cdi:PhysicalSegmentLayout-skipBlankRows",
    "cdi:PhysicalSegmentLayout-skipDataColumns",
    "cdi:PhysicalSegmentLayout-skipInitialSpace",
    "cdi:PhysicalSegmentLayout-skipRows",
    "cdi:PhysicalSegmentLayout-tableDirection",
    "cdi:PhysicalSegmentLayout-textDirection",
    "cdi:PhysicalSegmentLayout-treatConsecutiveDelimitersAsOne",
    "cdi:PhysicalSegmentLayout-trim",
    "cdi:PhysicalSegmentLayout_formats_LogicalRecord",
    "cdi:PhysicalSegmentLayout_has_ValueMapping",
    "cdi:PhysicalSegmentLayout_has_ValueMappingPosition",
    "cdi:PhysicalSegmentLayout_isDefinedBy_Concept",
    "cdi:PhysicalSegmentLocation",
    "cdi:PhysicalSegmentLocation-catalogDetails",
    "cdi:PhysicalSegmentLocation-identifier",
    "cdi:Population",
    "cdi:Population-timePeriodOfPopulation",
    "cdi:Population_isComposedOf_Unit",
    "cdi:Precedes",
    "cdi:Preserve",
    "cdi:PrimaryKey",
    "cdi:PrimaryKey-identifier",
    "cdi:PrimaryKeyComponent",
    "cdi:PrimaryKeyComponent-identifier",
    "cdi:PrimaryKeyComponent_correspondsTo_DataStructureComponent",
    "cdi:PrimaryKey_isComposedOf_PrimaryKeyComponent",
    "cdi:PrivateImage",
    "cdi:PrivateImage-effectiveDates",
    "cdi:PrivateImage-privacy",
    "cdi:ProcessingAgent",
    "cdi:ProcessingAgent_operatesOn_ProductionEnvironment",
    "cdi:ProcessingAgent_performs_Activity",
    "cdi:ProductionEnvironment",
    "cdi:ProductionEnvironment-description",
    "cdi:ProductionEnvironment-displayLabel",
    "cdi:ProductionEnvironment-identifier",
    "cdi:ProductionEnvironment-name",
    "cdi:ProvenanceInformation",
    "cdi:ProvenanceInformation-funding",
    "cdi:ProvenanceInformation-provenanceStatement",
    "cdi:ProvenanceInformation-recordCreationDate",
    "cdi:ProvenanceInformation-recordLastRevisionDate",
    "cdi:QualifiedMeasure",
    "cdi:QualifiedMeasure_refines_MeasureComponent",
    "cdi:Ratio",
    "cdi:RationaleDefinition",
    "cdi:RationaleDefinition-rationaleCode",
    "cdi:RationaleDefinition-rationaleDescription",
    "cdi:RecordRelation",
    "cdi:RecordRelation-catalogDetails",
    "cdi:RecordRelation-displayLabel",
    "cdi:RecordRelation-identifier",
    "cdi:RecordRelation-purpose",
    "cdi:RecordRelation-usage",
    "cdi:RecordRelation_has_InstanceVariableMap",
    "cdi:RecordRelation_maps_LogicalRecord",
    "cdi:Reference",
    "cdi:Reference-ddiReference",
    "cdi:Reference-deepLink",
    "cdi:Reference-description",
    "cdi:Reference-location",
    "cdi:Reference-nonDdiReference",
    "cdi:Reference-semantic",
    "cdi:Reference-uri",
    "cdi:Reference-validType",
    "cdi:ReferenceValue",
    "cdi:ReferenceValueDomain",
    "cdi:ReferenceValue_correspondsTo_VariableValueComponent",
    "cdi:ReferenceValue_hasValueFrom_ReferenceValueDomain",
    "cdi:ReferenceVariable",
    "cdi:ReferenceVariable_takesValuesFrom_ReferenceValueDomain",
    "cdi:RepeatUntil",
    "cdi:RepeatWhile",
    "cdi:Replace",
    "cdi:RepresentedVariable",
    "cdi:RepresentedVariable-describedUnitOfMeasure",
    "cdi:RepresentedVariable-hasIntendedDataType",
    "cdi:RepresentedVariable-simpleUnitOfMeasure",
    "cdi:RepresentedVariable_takesSentinelValuesFrom_SentinelValueDomain",
    "cdi:RepresentedVariable_takesSubstantiveValuesFrom_SubstantiveValueDomain",
    "cdi:RevisableDatum",
    "cdi:RevisableDatum-vintage",
    "cdi:RevisableDatum_correspondsTo_Revision",
    "cdi:Revision",
    "cdi:Revision-algorithm",
    "cdi:Revision-identifier",
    "cdi:Revision-overview",
    "cdi:Rtl",
    "cdi:Rule",
    "cdi:Rule-identifier",
    "cdi:RuleBasedScheduling",
    "cdi:RuleBasedScheduling-schedulingType",
    "cdi:RuleBasedScheduling_has_Curator",
    "cdi:RuleBasedScheduling_has_RuleSet",
    "cdi:RuleSet",
    "cdi:RuleSet-identifier",
    "cdi:RuleSet_has_Rule",
    "cdi:Rule_hasPrecondition_ConditionalControlLogic",
    "cdi:ScopedMeasure",
    "cdi:ScopedMeasure-frequency",
    "cdi:ScopedMeasure-identifier",
    "cdi:ScopedMeasure_circumscribes_DimensionalKeyDefinition",
    "cdi:ScopedMeasure_generates_RevisableDatum",
    "cdi:ScopedMeasure_restricts_QualifiedMeasure",
    "cdi:SegmentByText",
    "cdi:SegmentByText-characterLength",
    "cdi:SegmentByText-endCharacterPosition",
    "cdi:SegmentByText-endLine",
    "cdi:SegmentByText-startCharacterPosition",
    "cdi:SegmentByText-startLine",
    "cdi:Selector",
    "cdi:SentinelConceptualDomain",
    "cdi:SentinelValueDomain",
    "cdi:SentinelValueDomain-platformType",
    "cdi:SentinelValueDomain_isDescribedBy_ValueAndConceptDescription",
    "cdi:SentinelValueDomain_takesConceptsFrom_SentinelConceptualDomain",
    "cdi:SentinelValueDomain_takesValuesFrom_EnumerationDomain",
    "cdi:Sequence",
    "cdi:SequencePosition",
    "cdi:SequencePosition-identifier",
    "cdi:SequencePosition-value",
    "cdi:SequencePosition_indexes_Activity",
    "cdi:Sequence_has_SequencePosition",
    "cdi:Service",
    "cdi:Some",
    "cdi:SpatialCoordinate",
    "cdi:SpatialCoordinate-content",
    "cdi:SpatialCoordinate-coordinateType",
    "cdi:SpatialPoint",
    "cdi:SpatialPoint-xCoordinate",
    "cdi:SpatialPoint-yCoordinate",
    "cdi:SpecializationRole",
    "cdi:Start",
    "cdi:Starts",
    "cdi:Statistic",
    "cdi:Statistic-computationBase",
    "cdi:Statistic-content",
    "cdi:Statistic-isWeighted",
    "cdi:Statistic-typeOfNumericValue",
    "cdi:StatisticalClassification",
    "cdi:StatisticalClassification-allowsDuplicates",
    "cdi:StatisticalClassification-availableLanguage",
    "cdi:StatisticalClassification-catalogDetails",
    "cdi:StatisticalClassification-changeFromBase",
    "cdi:StatisticalClassification-copyright",
    "cdi:StatisticalClassification-displayLabel",
    "cdi:StatisticalClassification-isCurrent",
    "cdi:StatisticalClassification-isFloating",
    "cdi:StatisticalClassification-purposeOfVariant",
    "cdi:StatisticalClassification-rationale",
    "cdi:StatisticalClassification-releaseDate",
    "cdi:StatisticalClassification-updateChanges",
    "cdi:StatisticalClassification-usage",
    "cdi:StatisticalClassification-validDates",
    "cdi:StatisticalClassificationRelationship",
    "cdi:StatisticalClassificationRelationship-identifier",
    "cdi:StatisticalClassificationRelationship-semantics",
    "cdi:StatisticalClassificationRelationship_hasSource_StatisticalClassification",
    "cdi:StatisticalClassificationRelationship_hasTarget_StatisticalClassification",
    "cdi:StatisticalClassification_has_ClassificationItem",
    "cdi:StatisticalClassification_has_ClassificationItemPosition",
    "cdi:StatisticalClassification_has_LevelStructure",
    "cdi:StatisticalClassification_isIndexedBy_ClassificationIndex",
    "cdi:StatisticalClassification_isMaintainedBy_Organization",
    "cdi:StatisticalClassification_isPredecessorOf_StatisticalClassification",
    "cdi:StatisticalClassification_isSuccessorOf_StatisticalClassification",
    "cdi:StatisticalClassification_isVariantOf_StatisticalClassification",
    "cdi:Step",
    "cdi:Step-script",
    "cdi:Step-scriptingLanguage",
    "cdi:Step_hasSubStep_Step",
    "cdi:Step_produces_Parameter",
    "cdi:Step_receives_Parameter",
    "cdi:StructureSpecification",
    "cdi:StructureSpecification-reflexive",
    "cdi:StructureSpecification-symmetric",
    "cdi:StructureSpecification-transitive",
    "cdi:SubstantiveConceptualDomain",
    "cdi:SubstantiveValueDomain",
    "cdi:SubstantiveValueDomain_isDescribedBy_ValueAndConceptDescription",
    "cdi:SubstantiveValueDomain_takesConceptsFrom_SubstantiveConceptualDomain",
    "cdi:SubstantiveValueDomain_takesValuesFrom_EnumerationDomain",
    "cdi:SyntheticIdComponent",
    "cdi:Telephone",
    "cdi:Telephone-effectiveDates",
    "cdi:Telephone-isPreferred",
    "cdi:Telephone-privacy",
    "cdi:Telephone-telephoneNumber",
    "cdi:Telephone-typeOfTelephone",
    "cdi:TemporalConstraints",
    "cdi:TemporalControlConstruct",
    "cdi:TemporalControlConstruct-temporalControl",
    "cdi:TextPositionSelector",
    "cdi:TextPositionSelector-end",
    "cdi:TextPositionSelector-start",
    "cdi:TimeRole",
    "cdi:TimeRole-time",
    "cdi:Total",
    "cdi:TypedString",
    "cdi:TypedString-content",
    "cdi:TypedString-typeOfContent",
    "cdi:Unit",
    "cdi:Unit-catalogDetails",
    "cdi:Unit-definition",
    "cdi:Unit-displayLabel",
    "cdi:Unit-identifier",
    "cdi:Unit-name",
    "cdi:UnitSegmentLayout",
    "cdi:UnitType",
    "cdi:UnitType-descriptiveText",
    "cdi:Unit_has_UnitType",
    "cdi:Universe",
    "cdi:Universe-isInclusive",
    "cdi:ValidOnly",
    "cdi:ValueAndConceptDescription",
    "cdi:ValueAndConceptDescription-classificationLevel",
    "cdi:ValueAndConceptDescription-description",
    "cdi:ValueAndConceptDescription-formatPattern",
    "cdi:ValueAndConceptDescription-identifier",
    "cdi:ValueAndConceptDescription-logicalExpression",
    "cdi:ValueAndConceptDescription-maximumValueExclusive",
    "cdi:ValueAndConceptDescription-maximumValueInclusive",
    "cdi:ValueAndConceptDescription-minimumValueExclusive",
    "cdi:ValueAndConceptDescription-minimumValueInclusive",
    "cdi:ValueAndConceptDescription-regularExpression",
    "cdi:ValueDomain",
    "cdi:ValueDomain-catalogDetails",
    "cdi:ValueDomain-displayLabel",
    "cdi:ValueDomain-identifier",
    "cdi:ValueDomain-recommendedDataType",
    "cdi:ValueMapping",
    "cdi:ValueMapping-decimalPositions",
    "cdi:ValueMapping-defaultDecimalSeparator",
    "cdi:ValueMapping-defaultDigitGroupSeparator",
    "cdi:ValueMapping-defaultValue",
    "cdi:ValueMapping-format",
    "cdi:ValueMapping-identifier",
    "cdi:ValueMapping-isRequired",
    "cdi:ValueMapping-length",
    "cdi:ValueMapping-maximumLength",
    "cdi:ValueMapping-minimumLength",
    "cdi:ValueMapping-nullSequence",
    "cdi:ValueMapping-numberPattern",
    "cdi:ValueMapping-physicalDataType",
    "cdi:ValueMapping-scale",
    "cdi:ValueMappingPosition",
    "cdi:ValueMappingPosition-identifier",
    "cdi:ValueMappingPosition-value",
    "cdi:ValueMappingPosition_indexes_ValueMapping",
    "cdi:ValueMappingRelationship",
    "cdi:ValueMappingRelationship-identifier",
    "cdi:ValueMappingRelationship-semantics",
    "cdi:ValueMappingRelationship_hasSource_ValueMapping",
    "cdi:ValueMappingRelationship_hasTarget_ValueMapping",
    "cdi:ValueMapping_formats_DataPoint",
    "cdi:ValueMapping_uses_PhysicalSegmentLocation",
    "cdi:VariableCollection",
    "cdi:VariableCollection-allowsDuplicates",
    "cdi:VariableCollection-displayLabel",
    "cdi:VariableCollection-groupingSemantic",
    "cdi:VariableCollection-identifier",
    "cdi:VariableCollection-name",
    "cdi:VariableCollection-purpose",
    "cdi:VariableCollection-usage",
    "cdi:VariableCollection_has_ConceptualVariable",
    "cdi:VariableCollection_has_VariablePosition",
    "cdi:VariableCollection_isDefinedBy_Concept",
    "cdi:VariableDescriptorComponent",
    "cdi:VariableDescriptorComponent_isDefinedBy_DescriptorVariable",
    "cdi:VariableDescriptorComponent_refersTo_VariableValueComponent",
    "cdi:VariablePosition",
    "cdi:VariablePosition-identifier",
    "cdi:VariablePosition-value",
    "cdi:VariablePosition_indexes_ConceptualVariable",
    "cdi:VariableRelationship",
    "cdi:VariableRelationship-identifier",
    "cdi:VariableRelationship-semantics",
    "cdi:VariableRelationship_hasSource_ConceptualVariable",
    "cdi:VariableRelationship_hasTarget_ConceptualVariable",
    "cdi:VariableStructure",
    "cdi:VariableStructure-identifier",
    "cdi:VariableStructure-name",
    "cdi:VariableStructure-purpose",
    "cdi:VariableStructure-semantics",
    "cdi:VariableStructure-specification",
    "cdi:VariableStructure-topology",
    "cdi:VariableStructure-totality",
    "cdi:VariableStructure_has_VariableRelationship",
    "cdi:VariableStructure_structures_VariableCollection",
    "cdi:VariableValueComponent",
    "cdi:WebLink",
    "cdi:WebLink-effectiveDates",
    "cdi:WebLink-isPreferred",
    "cdi:WebLink-privacy",
    "cdi:WebLink-typeOfWebsite",
    "cdi:WebLink-uri",
    "cdi:WideDataSet",
    "cdi:WideDataStructure",
    "cdi:WideKey",
    "cdi:WideKeyMember",
    "cdi:XorJoin",
    "cdi:XorSplit",
})

RESERVED_KEYS = {"@context", "@graph", "@id", "@type", "id", "type"}
ALLOWED_RDFS = {"http://www.w3.org/2000/01/rdf-schema#label",
                "http://www.w3.org/2000/01/rdf-schema#comment"}


def is_official_cdi(iri: str) -> bool:
    """True if a full DDI-CDI IRI matches one of the cdi:-prefixed terms."""
    return iri.startswith(CDI_NS) and ("cdi:" + iri[len(CDI_NS):]) in DDI_CDI_TERMS


def expand(context: dict, term: str) -> str | None:
    """Expand a JSON key or type through the document's own @context.

    Returns the full IRI, or None if the term cannot be resolved.
    Accepts explicit prefixes ("cdi:CodeList") as well as context-declared
    short terms ("CodeList" -> official namespace, "label" -> rdfs:label).
    """
    if ":" in term:
        prefix, suffix = term.split(":", 1)
        ns = context.get(prefix)
        return ns + suffix if isinstance(ns, str) else None
    if term in context:
        target = context[term]
        if isinstance(target, str):
            if ":" in target:
                prefix, suffix = target.split(":", 1)
                ns = context.get(prefix)
                return ns + suffix if isinstance(ns, str) else None
            return target
        if isinstance(target, dict):
            iri = target.get("@id")
            if isinstance(iri, str) and ":" in iri:
                prefix, suffix = iri.split(":", 1)
                ns = context.get(prefix)
                return ns + suffix if isinstance(ns, str) else None
            return iri if isinstance(iri, str) else None
    # bare class/term names fall back to the official namespace
    return CDI_NS + term


class Reporter:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.infos: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)


def node_types(node: dict) -> list[str]:
    raw = node.get("@type", node.get("type"))
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


def collect_ids(graph: list[dict]) -> set[str]:
    ids = set()
    def walk(obj):
        if isinstance(obj, dict):
            if "@id" in obj or "id" in obj:
                ids.add(obj.get("@id") or obj.get("id"))
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)
    for node in graph:
        walk(node)
    return ids


def check_uri_resolution(rep: Reporter, graph: list[dict], offline: bool) -> None:
    """Resolve full http(s) URIs present in the graph (skipped with --offline)."""
    if offline:
        rep.info("--offline: URI resolution skipped")
        return
    iris = set()
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("@id", "id") and isinstance(v, str) and v.startswith("http"):
                    iris.add(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)
    for node in graph:
        walk(node)
    for iri in sorted(iris):
        try:
            req = urllib.request.Request(iri, method="HEAD",
                                         headers={"User-Agent": "rdm-dash-validator"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = "unreachable"
        status = "OK" if code == 200 else ("expected" if code in (404, 405) else str(code))
        rep.info(f"URI {iri} -> HTTP {code} ({status})")


def find_datapoints(graph: list[dict]) -> list[dict]:
    found: list[dict] = []

    def walk(obj) -> None:
        if isinstance(obj, dict):
            if any(t in ("cdi:DataPoint", "@vocab:DataPoint") or t == "DataPoint"
                   or t.endswith("DataPoint") for t in node_types(obj)):
                found.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    for node in graph:
        walk(node)
    return found


def find_node(graph: list[dict], nid: str) -> dict | None:
    for n in graph:
        if n.get("id") == nid or n.get("@id") == nid:
            return n
    return None


def validate(graph: list[dict], context: dict, df: pd.DataFrame, csv_name: str,
             rep: Reporter) -> None:
    # ---- 3/4. types and predicates -----------------------------------------
    ids = collect_ids(graph)
    for node in graph:
        nid = node.get("@id") or node.get("id", "(no id)")
        for type_val in node_types(node):
            iri = expand(context, type_val)
            if iri is None:
                rep.error(f"{nid}: unknown type {type_val!r}")
            elif iri.startswith(TUE_NS):
                rep.info(f"{nid}: tue: extension type {type_val!r}")
            elif iri.startswith(CDI_NS) and not is_official_cdi(iri):
                rep.error(f"{nid}: type {type_val!r} -> {iri} is not an official DDI-CDI term")
        for key in node:
            if key in RESERVED_KEYS:
                continue
            iri = expand(context, key)
            if iri is None:
                rep.error(f"{nid}: unknown predicate {key!r}")
            elif iri.startswith(TUE_NS):
                rep.info(f"{nid}: tue: extension predicate {key!r}")
            elif iri.startswith(RDFS_NS):
                if iri not in ALLOWED_RDFS:
                    rep.error(f"{nid}: disallowed rdfs predicate {key!r}")
            elif iri.startswith(RDF_NS):
                continue
            elif iri.startswith(CDI_NS) and not is_official_cdi(iri):
                rep.error(f"{nid}: predicate {key!r} -> {iri} is not an official DDI-CDI term")

    # ---- 5. blank-node referential integrity --------------------------------
    for node in graph:
        nid = node.get("@id") or node.get("id", "(no id)")
        refs: list[str] = []
        def gather(obj):
            if isinstance(obj, dict):
                if "@id" in obj or "id" in obj:
                    refs.append(obj.get("@id") or obj.get("id"))
                else:
                    for sub in obj.values():
                        gather(sub)
            elif isinstance(obj, list):
                for x in obj:
                    gather(x)
        for key, value in node.items():
            if key not in RESERVED_KEYS:
                gather(value)
        for ref in refs:
            if isinstance(ref, str) and ref.startswith("_:") and ref not in ids:
                rep.error(f"{nid}: dangling reference -> {ref}")

    # ---- 6. DataPoints -------------------------------------------------------
    dpoints = find_datapoints(graph)
    study = find_node(graph, "_:study")
    if study is None:
        rep.error("missing _:study wrapper node")
    wds = find_node(graph, "_:wds1")
    if wds is None:
        rep.error("missing _:wds1 node")

    declared = None
    if study is not None:
        rc = study.get("tue:respondentCount")
        if isinstance(rc, int):
            declared = rc
        elif isinstance(rc, str) and rc.isdigit():
            declared = int(rc)
    if declared is not None and declared != len(dpoints):
        rep.error(f"tue:respondentCount ({declared}) != DataPoint count ({len(dpoints)})")
    if len(df) != len(dpoints):
        rep.error(f"CSV rows ({len(df)}) != DataPoint count ({len(dpoints)})")

    seen: set[str] = set()
    csv_ids = df["ID"].astype(str).tolist()
    for dp in dpoints:
        ident = dp.get("tue:identifierValue")
        if ident is None:
            rep.error(f"DataPoint missing tue:identifierValue: {json.dumps(dp)[:80]}")
            continue
        if ident in seen:
            rep.error(f"duplicate DataPoint identifier {ident!r}")
        seen.add(ident)
        if ident not in csv_ids:
            rep.error(f"DataPoint identifier {ident!r} not found in CSV")

        measures = dp.get("tue:measureValue")
        if not isinstance(measures, list):
            rep.error(f"DataPoint {ident}: missing tue:measureValue list")
            continue
        by_ref = {}
        for m in measures:
            if isinstance(m, dict):
                by_ref[m.get("tue:variableRef")] = m.get("tue:value")
        for ref in ("_:iv1", "_:iv2", "_:iv3"):
            v = by_ref.get(ref)
            if v is not None and (not isinstance(v, int) or not 1 <= v <= 5):
                rep.error(f"DataPoint {ident}: {ref} outside Likert 1-5: {v!r}")
        v4 = by_ref.get("_:iv4")
        if v4 is not None and v4 not in (1, 2):
            rep.error(f"DataPoint {ident}: _:iv4 not Yes(1)/No(2): {v4!r}")
        v5 = by_ref.get("_:iv5")
        if v5 is not None and (not isinstance(v5, int) or not 1 <= v5 <= 5):
            rep.error(f"DataPoint {ident}: _:iv5 outside star 1-5: {v5!r}")
        if v4 == 2:
            if v5 is not None:
                rep.error(f"DataPoint {ident}: skip logic: iv4=No but iv5={v5!r}")
        if v4 == 1 and v5 is None:
            rep.error(f"DataPoint {ident}: skip logic: iv4=Yes but iv5 missing")

        ts = dp.get("tue:responseTimestamps")
        if not isinstance(ts, dict):
            rep.error(f"DataPoint {ident}: missing tue:responseTimestamps")
        else:
            start, end = ts.get("tue:startTime"), ts.get("tue:completionTime")
            for label, t in (("startTime", start), ("completionTime", end)):
                if not isinstance(t, str):
                    rep.error(f"DataPoint {ident}: {label} not a string: {t!r}")
                    continue
                try:
                    datetime.fromisoformat(t)
                except ValueError:
                    rep.error(f"DataPoint {ident}: invalid ISO {label}: {t!r}")
            if isinstance(start, str) and isinstance(end, str):
                try:
                    if datetime.fromisoformat(start) > datetime.fromisoformat(end):
                        rep.error(f"DataPoint {ident}: startTime > completionTime")
                except ValueError:
                    pass

    # ---- 8. cross-validate measure values against the CSV --------------------
    iv_cols = {
        "_:iv1": "Finding the DMP template in the TU/e Research Cockpit was easy",
        "_:iv2": "The process of completing my DMP was easy",
        "_:iv3": "The instructions and guidance provided by the system were clear",
        "_:iv4": "Did you have contact with a data steward?",
        "_:iv5": "How helpful was the advice of the data steward?",
        "_:iv6": "If you could change anything about the DMP experience, what would it be?",
    }
    likert = {"Strongly Disagree": 1, "Disagree": 2, "Neutral": 3, "Agree": 4, "Strongly Agree": 5}
    yesno = {"Yes": 1, "No": 2}
    mismatches = 0
    dp_by_id = {d.get("tue:identifierValue"): d for d in dpoints}
    for _, row in df.iterrows():
        ident = str(int(row["ID"]))
        dp = dp_by_id.get(ident)
        if dp is None:
            continue
        measures = {m.get("tue:variableRef"): m.get("tue:value")
                    for m in dp.get("tue:measureValue", []) if isinstance(m, dict)}
        for ref, col in iv_cols.items():
            raw = row[col]
            if pd.isna(raw):
                expected = None
            elif ref in ("_:iv1", "_:iv2", "_:iv3"):
                expected = likert.get(str(raw).strip())
            elif ref == "_:iv4":
                expected = yesno.get(str(raw).strip())
            elif ref == "_:iv5":
                expected = int(float(raw))
            else:
                expected = str(raw).strip()
            got = measures.get(ref)
            if got != expected:
                mismatches += 1
                rep.error(f"CSV/JSON mismatch row {ident} {ref}: CSV {expected!r} vs JSON {got!r}")
                if mismatches > 10:
                    break
        if mismatches > 10:
            break

    pds = find_node(graph, "_:pds1")
    if pds is not None:
        fn = pds.get("cdi:PhysicalDataSet-physicalFileName")
        if fn != csv_name:
            rep.error(f"physicalFileName {fn!r} != source CSV {csv_name!r}")

    rep.info(f"{len(dpoints)} DataPoints checked")


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    jsonld_path = base / "data" / "feedback-survey-dataset.jsonld"
    csv_path = base / "data" / "feedback-survey-responses.csv"

    parser = argparse.ArgumentParser(description="Validate the DMP feedback survey JSON-LD dataset")
    parser.add_argument("jsonld", nargs="?", default=str(jsonld_path))
    parser.add_argument("csv", nargs="?", default=str(csv_path))
    parser.add_argument("--offline", action="store_true", help="skip URI resolution")
    args = parser.parse_args()

    rep = Reporter()

    # ---- 1. parse (strict JSON: embedded comments would fail here) ----------
    try:
        doc = json.loads(Path(args.jsonld).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FATAL: invalid JSON in {args.jsonld}: {e}", file=sys.stderr)
        sys.exit(1)

    context = doc.get("@context", {})
    if not isinstance(context, dict) or context.get("cdi") != CDI_NS:
        rep.error(f"@context missing official cdi namespace (expected {CDI_NS})")
    if "@vocab" in context:
        rep.info("@vocab present in @context; predicates rely on explicit cdi:/tue:/rdfs: prefixes")

    graph = doc.get("@graph")
    if not isinstance(graph, list):
        print("FATAL: missing @graph array", file=sys.stderr)
        sys.exit(1)

    # ---- 2. CSV --------------------------------------------------------------
    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    df.columns = [c.strip().rstrip("\u00a0").strip() for c in df.columns]

    validate(graph, context, df, Path(args.csv).name, rep)
    check_uri_resolution(rep, graph, args.offline)

    for msg in rep.infos:
        print(f"  info: {msg}")
    for msg in rep.errors:
        print(f"  ERROR: {msg}", file=sys.stderr)

    ok = not rep.errors
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'} "
          f"({len(rep.infos)} infos, {len(rep.errors)} errors, "
          f"vocabulary={len(DDI_CDI_TERMS)} terms)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
