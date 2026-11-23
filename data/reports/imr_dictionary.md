# IMR data dictionary (summary)

Summarized from the DMHC data dictionary PDF (`imrdatadictionary.pdf`) and checked against the real file.

| Field | Type (dictionary) | Meaning | Notes from profiling |
|---|---|---|---|
| ReferenceID | Plain text | Unique identifier for the case | 39 exact duplicate rows exist in the file; dropped. Prefix encodes type + year (e.g. MN26-, EI02-) |
| ReportYear | Number | Year the case was reported | 2001-2026; 2001 and the current year are partial |
| DiagnosisCategory | Plain text | Main diagnosis category | ~48 values |
| DiagnosisSubCategory | Plain text | Secondary diagnosis category | |
| TreatmentCategory | Plain text | Main treatment category | ~58 values; abbreviated labels (e.g. 'Diag Imag & Screen') |
| TreatmentSubCategory | Plain text | Secondary treatment category | ~500 values |
| Determination | Plain text | Whether the plan's decision was upheld or overturned | 'Overturned Decision of Health Plan' / 'Upheld Decision of Health Plan' |
| Type | Plain text | Case type: Medical Necessity, Experimental/Investigational, Urgent Care | |
| AgeRange | (dictionary lists 'PaientAge', Number) | Patient age | File has banded ranges ('51 to 64', '65+'), not a number - dictionary is out of date |
| PatientGender | Plain text | Patient gender | Female / Male / Other / blank |
| IMRType | (not in dictionary) | Standard vs Expedited review | Present in the file |
| DaysToReview | (not in dictionary) | Days taken to review | Present in the file |
| DaysToAdopt | (not in dictionary) | Days to adopt the decision | Post-decision: target leakage for M3 |
| Findings | Plain text | Summary of the case findings (physician reviewer) | Free text; states the conclusion (leakage for M3) |

Discrepancies between the dictionary and the file are recorded above; the pipeline validates against the file's real columns.

## Raw dictionary text (extracted)

```
Data Dictionary   
Field Title Field Name 
Data 
type Description 
 
ReferenceID ReferenceID 
Plain 
Text Unique identifier for the case. 
ReportYear ReportYear Number Year the case was reported. 
DiagnosisCategory DiagnosisCategory 
Plain 
Text The main diagnosis category. 
DiagnosisSubCategory DiagnosisSubCategory 
Plain 
Text The secondary diagnosis category. 
TreatmentCategory TreatmentCategory 
Plain 
Text The main treatment category. 
TreatmentSubCategory TreatmentSubCategory
Plain 
Text The secondary treatment category. 
Determination Determination 
Plain 
Text 
Indicates if the determination was 
upheld or overturned. 
Type Type 
Plain 
Text 
Indicates the type of case 
(Experimental/Investigational, Urgent 
Care, Medical Necessity) 
PaientAge PaientAge Number The age of the patient. 
PatientGender PatientGender 
Plain 
Text The gender of the patient. 
Findings Findings 
Plain 
Text A summary of the case findings. 
1/1
```
