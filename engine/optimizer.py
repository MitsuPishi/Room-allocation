from ortools.sat.python import cp_model
import pandas as pd
import numpy as np
import time

class ProgressCallback(cp_model.CpSolverSolutionCallback):
    """OR-Tools callback to track optimization progress in real-time."""
    
    def __init__(self, progress_handler=None):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.progress_handler = progress_handler
        self.solution_count = 0
        self.last_update_time = time.time()
        self.update_interval = 0.5  # Update UI every 0.5 seconds
        
    def OnSolutionCallback(self):
        """Called by OR-Tools every time a new solution is found."""
        current_time = time.time()
        
        # Throttle updates to avoid overwhelming the UI
        if current_time - self.last_update_time < self.update_interval:
            return
        
        self.solution_count += 1
        current_obj = self.ObjectiveValue()
        best_bound = self.BestObjectiveBound()
        
        if self.progress_handler:
            # Calculate optimality gap
            if best_bound > 0 and current_obj > 0:
                gap = max(0, (best_bound - current_obj) / best_bound * 100)
            else:
                gap = 0
                
            self.progress_handler(
                current_objective=current_obj,
                best_bound=best_bound,
                solution_count=self.solution_count,
                gap_percent=gap
            )
        
        self.last_update_time = current_time


class DormOptimizationEngine:
    def __init__(self, df_students: pd.DataFrame, df_rooms: pd.DataFrame, matrix: np.ndarray):
        self.students = df_students.to_dict(orient='records')
        self.rooms = df_rooms.to_dict(orient='records')
        self.matrix = matrix
        self.model = cp_model.CpModel()
        
        self.x = {}  # Assignment variables
        self.room_occupancy = {}  # Room occupancy tracking
        self.progress_callback = None  # Optional progress callback
        
        # Precompute significant pairings for efficiency
        threshold = 5
        self.significant_pairs = []
        for i in range(len(self.students)):
            for j in range(i + 1, len(self.students)):
                if abs(matrix[i][j]) > threshold:
                    self.significant_pairs.append((i, j, int(matrix[i][j])))

    def set_progress_callback(self, callback):
        """Set a callback function to track optimization progress.
        
        Callback signature: callback(current_objective, best_bound, solution_count, gap_percent)
        """
        self.progress_callback = callback

    def build_model(self):
        """Build optimized CP-SAT model with reduced variable count."""
        n_students = len(self.students)
        n_rooms = len(self.rooms)
        
        # 1. Decision Variables: x[s, r] == 1 if student s is in room r
        for s_idx in range(n_students):
            for r_idx in range(n_rooms):
                self.x[(s_idx, r_idx)] = self.model.NewBoolVar(f'x_{s_idx}_{r_idx}')

        # 2. Constraint: Every student assigned exactly once
        for s_idx in range(n_students):
            self.model.AddExactlyOne([self.x[(s_idx, r_idx)] for r_idx in range(n_rooms)])

        # 3. Constraint: Room capacity limits
        for r_idx, r in enumerate(self.rooms):
            occupancy = [self.x[(s_idx, r_idx)] for s_idx in range(n_students)]
            self.model.Add(sum(occupancy) <= r['capacity'])
            self.room_occupancy[r_idx] = sum(occupancy)

        # 4. Objective: Pairwise links ONLY for significant pairings in shared rooms
        objective_terms = []
        
        for i, j, score in self.significant_pairs:
            for r_idx in range(n_rooms):
                # y[i,j,r] = 1 iff both students i and j are in room r
                y_var = self.model.NewBoolVar(f'y_{i}_{j}_{r_idx}')
                
                # Efficient reification: y = 1 only if x[i,r] AND x[j,r]
                self.model.AddImplication(y_var, self.x[(i, r_idx)])
                self.model.AddImplication(y_var, self.x[(j, r_idx)])
                self.model.AddBoolOr([
                    self.x[(i, r_idx)].Not(),
                    self.x[(j, r_idx)].Not(),
                    y_var
                ])
                
                objective_terms.append(score * y_var)

        # 5. Global Maximization Objective
        if objective_terms:
            self.model.Maximize(sum(objective_terms))

    def solve(self, time_limit_sec: int = 30):
        """Solve with optimized solver parameters and real-time progress tracking."""
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_sec)
        solver.parameters.num_search_workers = 4
        solver.parameters.log_search_progress = False
        
        # Create progress callback with user's handler
        progress_callback = ProgressCallback(progress_handler=self.progress_callback)
        
        # Solve with callback
        status = solver.Solve(self.model, progress_callback)
        
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
                    break
                    
        return pd.DataFrame(assignments), "Optimal" if status == cp_model.OPTIMAL else "Feasible"