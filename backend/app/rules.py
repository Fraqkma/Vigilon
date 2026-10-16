import time

class TemporalRuleEvaluator:
    """Require a continuous observation window before a rule can fire."""
    def __init__(self,clock=time.monotonic):self.clock=clock;self._since={};self._scenarios={}
    def clear(self,camera_id):
        for key in [key for key in self._since if key[0]==camera_id]:self._since.pop(key,None)
        for key in [key for key in self._scenarios if key[0]==camera_id]:self._scenarios.pop(key,None)
    def scenario(self,camera_id,module_id,scenario_id,grace=1.0,cooldown=10.0):
        from .scenario_rules import ScenarioEvaluator
        key=(camera_id,module_id,scenario_id)
        if key not in self._scenarios:self._scenarios[key]=ScenarioEvaluator(grace,cooldown)
        return self._scenarios[key]
    def accepts(self,camera,rule):
        key=(camera.id,rule.id);observed=self.clock();state=self._since.get(key)
        if not state or observed-state[1]>max(2.0,3/max(1,camera.processing_fps or 2)):state=(observed,observed)
        else:state=(state[0],observed)
        self._since[key]=state
        return observed-state[0]>=rule.min_duration
