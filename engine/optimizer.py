from ortools.sat.python import cp_model
import pandas as pd
import numpy as np

class DormOptimizationEngine:
    def __init__(self, df_students: pd.DataFrame, df_rooms: pd.DataFrame, matrix: np.ndarray):
        self.students = df_students.to_dict(orient='records')
        self.rooms = df_rooms.to_dict(orient='records')
        self.matrix = matrix
        self.model = cp_model.CpModel()
        
        self.x = {}  # Assignment variables
        self.y = {}  # Pairwise co-location variables

    def build_model(self):
        # 1. Decision Variables: x[s, r] == 1 if student s is in room r
        for s_idx, s in enumerate(self.students):
            for r_idx, r in enumerate(self.rooms):
                self.x[(s_idx, r_idx)] = self.model.NewBoolVar(f'x_{s_idx}_{r_idx}')

        # 2. Constraint: Every student assigned exactly once
        for s_idx in range(len(self.students)):
            self.model.AddExactlyOne([self.x[(s_idx, r_idx)] for r_idx in range(len(self.rooms))])

        # 3. Constraint: Room capacity limits
        for r_idx, r in enumerate(self.rooms):
            self.model.Add(
                sum(self.x[(s_idx, r_idx)] for s_idx in range(len(self.students))) <= r['capacity']
            )

        # 4. Objective & Graph Edge Tracking: Pairwise links inside rooms
        objective_terms = []
        for r_idx in range(len(self.rooms)):
            for i in range(len(self.students)):
                for j in range(i + 1, len(self.students)):
                    score = int(self.matrix[i][j])
                    
                    # Sparsification: Ignore non-consequential pairings to reduce variable bloat
                    if abs(score) > 5:
                        y_var = self.model.NewBoolVar(f'y_{i}_{j}_{r_idx}')
                        self.y[(i, j, r_idx)] = y_var
                        
                        # Reification: y_var is true IF both x[i, r] and x[j, r] are true
                        self.model.AddBoolOr([self.x[(i, r_idx)].Not(), self.x[(j, r_idx)].Not(), y_var])
                        
                        objective_terms.append(score * y_var)

        # 5. Global Maximization Objective
        self.model.Maximize(sum(objective_terms))

    def solve(self, time_limit_sec: int = 30):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_sec)
        # Enable multi-threading execution
        solver.parameters.num_search_workers = 4 
        
        status = solver.Solve(self.model)
        
        if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            return None, "Infeasible"
            
        # Parse Solution
        assignments = []
        for s_idx, s in enumerate(self.students):
            for r_idx, r in enumerate(self.rooms):
                if solver.Value(self.x[(s_idx, r_idx)]) == 1:
                    assignments.append({
                        "student_id": s["student_id"],
                        "student_name": s["name"],
                        "room_id": r["room_id"],
                        "room_name": r["room_name"]
                    })
                    
        return pd.DataFrame(assignments), "Optimal" if status == cp_model.OPTIMAL else "Feasible"