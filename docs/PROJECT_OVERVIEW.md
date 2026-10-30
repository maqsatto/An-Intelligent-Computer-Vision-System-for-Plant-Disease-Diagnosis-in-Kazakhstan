# AgroVision project scope

AgroVision studies recognition of visible leaf conditions from RGB photographs and provides an Android workflow for recording observations. Farmers and field workers need a photograph, crop context, a recoverable processing state and a history they can discuss with an agronomist. The degree of usefulness in actual field work still requires user discussions; it is not inferred from a running application.

## Problem and research question

Photographs from a controlled dataset do not establish performance on a different source or in Kazakhstan. The research question is the additional effect of using the known crop inside visual feature computation when the loss, allowable answers, data, training budget and test source are otherwise comparable. Crop conditioning and FiLM are established methods; the proposed contribution is a controlled empirical comparison and analysis of its uncertainty and limits.

The planned principal contrast is ResNet18 C1 minus C0 on a completely held-out source. G0 supplies a separate loss control. These configurations are a new experiment, distinct from the completed EfficientNet-B0 pilot. Source admission, grouping and a frozen protocol precede the main experiments.

## Objectives and expected results

- Audit source versions, rights, original labels, parent photographs and available independent groups before admitting a corpus.
- Compare the predefined research configurations on identical data and paired seeds; report crop-balanced macro-F1, a grouped interval for the paired difference and variation between seeds.
- Preserve per-image predictions, model/configuration hashes, exclusions and error analysis so the result can be checked and reproduced.
- Maintain the Android observation, private photograph, durable assessment and owner history workflow with explicit model availability and uncertainty.
- Establish access to independently collected local cases and expert annotation before making claims about Kazakhstan. Collection targets are planning estimates, not achieved sample sizes.

## Current implemented scope

The Android client uses Expo/React Native and a generated API client. FastAPI and a separate bounded worker share PostgreSQL. An observation contains one primary photograph, and asynchronous assessments use stable request IDs, immutable model pins/results, owner checks and lease fencing. Feedback is stored separately from model output.

The completed research pilot uses wheat, potato and tomato with nine source-label classes. Its measured internal test covers 153 photographs; the paired comparison with the earlier pilot uses 88 identical test photographs. The research runtime always returns `inconclusive`. These measurements do not validate the proposed ResNet18 experiment or local diagnostic performance.

There is no persistent offline queue, web client, validated diagnostic policy or completed external/local validation. Physical-phone camera testing and provider-backed OIDC verification remain open. Local photo storage is the implemented private adapter; deployment object storage is a later adapter.

## Technical evidence

- [Data provenance and measured pilot](development/DATA_AND_MODEL.md).
- [Reproducible model cases and errors](evaluation/MEASURED_CASES.md).
- [API and worker verification](development/VERIFICATION.md).
- [Android implementation and native emulator evidence](development/MOBILE_REPORT.md).
- [Requirements and acceptance criteria](foundation/planning/REQUIREMENTS_AND_TRACEABILITY.md).
- [Architecture and editable diagrams](foundation/architecture/SYSTEM_DESIGN.md).
- [API contract](foundation/contracts/API_CONTRACT.md).

The team and links are maintained in the root README. Research/configuration changes and application changes are committed under their respective responsibility owners. Actual review and acceptance evidence must be recorded as it occurs.
