# LiLT v3.1 training model: observed verification

Date: 2026-10-16 (Europe/Rome).

Git revision: `3be17a8ae7c15a4b33183044c70da9fe5591470f` plus the uncommitted training work described below. This is a record of checks executed during the session, not a claim that the final full repository suite was run by this worker.

Scope: `training/model.py`, `training/modal_train.py`, `tests/test_training_model.py`.

## Test-first evidence

1. Eight behavior tests were added before implementation. The first collection found the intentionally absent module; minimal signatures raising `NotImplementedError` were then created so the behavior tests could execute. Running `.venv/Scripts/python.exe -m pytest tests/test_training_model.py -q` produced **8 failed in 12.23s**, all on the expected unimplemented behavior.
2. Implemented full-image box normalization, whole-row/whole-word chunking, first-subword supervision, uncertain-word masking, prediction order, and practice split isolation. Seven tests passed; the real tiny LiLT prediction test exposed an invalid test configuration (24 hidden channels did not divide the layout attention heads). Corrected the tiny model configuration to 48 hidden channels, retaining every behavioral assertion.
3. Added a real tiny CPU training/save/reload smoke test using locally generated model and tokenizer files, without downloaded weights or mocked model internals. The default pytest temporary directory was blocked by the sandbox, so subsequent runs used explicit temporary directories under ignored `mnt/`.
4. The CPU training smoke and eight earlier tests passed: **9 passed in 21.65s** using `--basetemp=mnt/tmp-training-model-v31`.
5. Added a reviewed-dataset content-integrity test against a new unimplemented validator. Running `-k reviewed_dataset --basetemp=mnt/tmp-training-model-guard-v31` produced **1 failed, 9 deselected in 0.56s**, on its expected `NotImplementedError`.
6. Implemented reviewed v3.1 count, label, geometry, role-order, practice-isolation, manifest-split, and content-fingerprint validation. Running `.venv/Scripts/python.exe -m pytest tests/test_training_model.py -q --basetemp=mnt/tmp-training-model-final-v31` produced **10 passed in 13.68s**.

## Additional observed checks

- Word F1 delegates to the shared `training.evaluation.word_metrics` implementation; the model wrapper adds word accuracy and explicit zero-coverage roles.
- Actual tiny CPU training saved and reloaded a LiLT checkpoint with the expected role map. Epoch logs contain validation scores only; test predictions are generated after selecting the validation checkpoint.
- Modal 1.5.5 imported `training.modal_train` and its function decorators successfully, without launching a job. This validated local import only, not the remote service constraints. The subsequent coordinating-worker launch was rejected before its local entrypoint/GPU call because the service requires `scaledown_window` between 2 and 3600 seconds. The coordinator changed the value from 1 to 2 and resealed the source manifest before relaunch; that change did not alter the reviewed dataset content.
- `.venv/Scripts/python.exe -m py_compile training/modal_train.py` succeeded after restricting the base snapshot download to `config.json`, safetensors weights, and the three tokenizer JSON files.
- Modal CLI help confirmed `python -m modal run -m training.modal_train` is valid module invocation syntax.
- Primary model configuration was checked at <https://huggingface.co/nielsr/lilt-xlm-roberta-base/blob/main/config.json>: 514 positional embeddings and padding ID 1 support the configured 512-token total chunk length. The repository supplies `tokenizer.json`, avoiding an additional SentencePiece dependency.

## Limits

- These checks did not run a Modal training job, download model weights, or verify GPU training throughput.
- The final safetensors-only image download filter changed download selection, not model/chunk behavior. Only import and compilation were repeated after that metadata-only change.
- Full repository suite results and the actual training run must be recorded separately by the coordinating worker.

## Native metadata transport regression after completed GPU run

The GPU run completed and committed all model/JSON artifacts, but the local Modal
Python environment without Torch failed to deserialize the returned TorchVersion
subclass from torch.__version__. Saved JSON artifacts were unaffected.

A regression recursively checks exact built-in JSON types over the result of a
real tiny CPU training run. RED: **1 failed, 10 deselected in 10.76s**, on the
TorchVersion value. The fix casts dependency versions to built-in str. GREEN:
**11 passed in 12.61s**, using mnt/tmp-training-model-native-green. No GPU job or
retraining was launched for this fix. The executed run's original source hashes
remain in executed-training-provenance.json; current sources are separate.
