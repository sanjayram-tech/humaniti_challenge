# humaniti_challenge

Rating recorded online chess classes for kids as Excellent / Good / Average / Weak /
Quality issue, using a 3-layer rubric that AI and human reviewers share.

- [`rubric/RUBRIC.md`](rubric/RUBRIC.md): the scoring guide (start here)
- [`rubric/rubric.yaml`](rubric/rubric.yaml): machine-readable rubric
- [`rubric/calibration/reviewed_classes.yaml`](rubric/calibration/reviewed_classes.yaml): the 10 classes reviewers have already rated
- [`scoring/tier.py`](scoring/tier.py): turns gate results and scores into a tier

```sh
pip install pyyaml
python3 -m unittest -v   # checks the tier rules reproduce the reviewers' tiers
```
