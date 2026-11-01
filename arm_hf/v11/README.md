---
dataset_info:
  features:
  - name: instance_id
    dtype: string
  - name: problem_statement
    dtype: string
  - name: dependencies
    list: string
  - name: checkpoints
    dtype: string
  - name: agent_profiles
    list:
    - name: data
      struct:
      - name: age
        dtype: int64
      - name: first_name
        dtype: string
      - name: gender
        dtype: string
      - name: gender_pronoun
        dtype: string
      - name: last_name
        dtype: string
      - name: occupation
        dtype: string
      - name: public_info
        dtype: string
    - name: name
      dtype: string
  - name: agent_scenarios
    list:
    - name: data
      struct:
      - name: extra_info
        dtype: string
      - name: goal
        dtype: string
      - name: strategy_hint
        dtype: string
    - name: name
      dtype: string
  - name: agent_models
    list:
    - name: model
      dtype: string
    - name: name
      dtype: string
  - name: environment
    dtype: string
  - name: npcs
    dtype: int64
  - name: has_workspace
    dtype: bool
  - name: workspace_files
    list: string
  - name: has_utils
    dtype: bool
  - name: utils_files
    list: string
  - name: evaluator_code
    dtype: string
  - name: github_url
    dtype: string
  splits:
  - name: train
    num_bytes: 1012625
    num_examples: 357
  download_size: 369102
  dataset_size: 1012625
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---
