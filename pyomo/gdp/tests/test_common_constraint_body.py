#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright (c) 2008-2022
#  National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

import pyomo.common.unittest as unittest
from pyomo.core.expr.compare import assertExpressionsEqual
from pyomo.environ import Any, Block, ConcreteModel, Constraint, TransformationFactory, Var
from pyomo.gdp import Disjunct, Disjunction


class TestCommonConstraintBodyTransformation(unittest.TestCase):
    def create_nested_structure(self):
        """
        Creates a two-term Disjunction with on nested two-term Disjunction on
        the first Disjunct
        """
        m = ConcreteModel()
        m.outer_d1 = Disjunct()
        m.outer_d1.inner_d1 = Disjunct()
        m.outer_d1.inner_d2 = Disjunct()
        m.outer_d1.inner = Disjunction(expr=[m.outer_d1.inner_d1, m.outer_d1.inner_d2])
        m.outer_d2 = Disjunct()
        m.outer = Disjunction(expr=[m.outer_d1, m.outer_d2])
        return m

    def create_nested_model(self):
        """
        -100 <= x <= 102
        [-10 <= x <= 11, [x <= 3] v [x >= -17]] v [x == 0]
        """
        m = self.create_nested_structure()
        m.x = Var(bounds=(-100, 102))
        m.outer_d1.c = Constraint(expr=(-10, m.x, 11))
        m.outer_d1.inner_d1.c = Constraint(expr=m.x <= 3)
        m.outer_d1.inner_d2.c = Constraint(expr=m.x >= -7)
        m.outer_d2.c = Constraint(expr=m.x == 0)

        return m

    def test_transform_nested_model(self):
        m = self.create_nested_model()

        bt = TransformationFactory('gdp.common_constraint_body')
        bt.apply_to(m)

        # We expect: -10w_1 -7w_2 <= x <= 3w_1 + 11w_2

        cons = bt.get_transformed_constraints(m.x, m.outer)
        self.assertEqual(len(cons), 2)
        lb = cons[0]
        ub = cons[1]
        assertExpressionsEqual(
            self,
            lb.expr,
            -10.0 * m.outer_d1.inner_d1.binary_indicator_var
            - 7.0 * m.outer_d1.inner_d2.binary_indicator_var +
            0.0 * m.outer_d2.binary_indicator_var
            <= m.x,
        )
        assertExpressionsEqual(
            self,
            ub.expr,
            3.0 * m.outer_d1.inner_d1.binary_indicator_var
            + 11.0 * m.outer_d1.inner_d2.binary_indicator_var +
            0.0 * m.outer_d2.binary_indicator_var
            >= m.x,
        )

        # All the disjunctive constraints were transformed
        self.assertFalse(m.outer_d1.c.active)
        self.assertFalse(m.outer_d1.inner_d1.c.active)
        self.assertFalse(m.outer_d1.inner_d2.c.active)
        self.assertFalse(m.outer_d2.c.active)

        # There aren't any other constraints on the model other than what we
        # added
        self.assertEqual(
            len(
                list(
                    m.component_data_objects(
                        Constraint, active=True, descend_into=(Block, Disjunct)
                    )
                )
            ),
            2,
        )

    def test_transform_nested_model_no_0_terms(self):
        m = self.create_nested_model()
        m.outer_d2.c.deactivate()
        m.outer_d2.c2 = Constraint(expr=m.x == 101)

        bt = TransformationFactory('gdp.common_constraint_body')
        bt.apply_to(m)

        # We expect: -10w_1 -7w_2 + 101 y_2 <= x <= 3w_1 + 11w_2 + 101y_2

        cons = bt.get_transformed_constraints(m.x, m.outer)
        self.assertEqual(len(cons), 2)
        lb = cons[0]
        ub = cons[1]
        assertExpressionsEqual(
            self,
            lb.expr,
            -10.0 * m.outer_d1.inner_d1.binary_indicator_var
            - 7.0 * m.outer_d1.inner_d2.binary_indicator_var
            + 101.0 * m.outer_d2.binary_indicator_var
            <= m.x,
        )
        assertExpressionsEqual(
            self,
            ub.expr,
            3.0 * m.outer_d1.inner_d1.binary_indicator_var
            + 11.0 * m.outer_d1.inner_d2.binary_indicator_var
            + 101.0 * m.outer_d2.binary_indicator_var
            >= m.x,
        )

        # All the disjunctive constraints were transformed
        self.assertFalse(m.outer_d1.c.active)
        self.assertFalse(m.outer_d1.inner_d1.c.active)
        self.assertFalse(m.outer_d1.inner_d2.c.active)
        self.assertFalse(m.outer_d2.c2.active)

        # There aren't any other constraints on the model other than what we
        # added
        self.assertEqual(
            len(
                list(
                    m.component_data_objects(
                        Constraint, active=True, descend_into=(Block, Disjunct)
                    )
                )
            ),
            2,
        )

    def test_transformation_gives_up_without_enough_bound_info(self):
        """
        If we have unbounded variables and not enough bounding constraints,
        we want the transformation to just leave the bounding constraints
        be to be transformed later.
        """
        m = self.create_nested_structure()
        m.x = Var()
        m.y = Var(bounds=(4, 67))
        m.outer_d1.c = Constraint(Any)
        m.outer_d1.c[1] = m.x >= 3
        m.outer_d1.c[2] = 5 <= m.y
        m.outer_d1.inner_d1.c = Constraint(Any)
        m.outer_d1.inner_d1.c[1] = m.x >= 4
        m.outer_d1.inner_d2.c = Constraint(Any)
        m.outer_d1.inner_d2.c[1] = m.x >= 17
        m.outer_d2.c = Constraint(Any)
        m.outer_d2.c[1] = m.x <= 1
        m.outer_d2.c[2] = m.y <= 66
        m.outer_d2.c[3] = m.x >= 2

        # y constraints should be fully transformed, and x can do lower but not
        # upper.

        bt = TransformationFactory('gdp.common_constraint_body')
        bt.apply_to(m)

        # We expect: 4w_1 + 17w_2 + 2y_2 <= x
        #            5w_1 + 5w_2 + 4y_2 <= y <= 67w_1 + 67w_2 + 66y_2

        cons = bt.get_transformed_constraints(m.x, m.outer)
        self.assertEqual(len(cons), 1)
        lb = cons[0]
        assertExpressionsEqual(
            self,
            lb.expr,
            4.0*m.outer_d1.inner_d1.binary_indicator_var +
            17.0*m.outer_d1.inner_d2.binary_indicator_var +
            2.0*m.outer_d2.binary_indicator_var <= m.x
        )

        cons = bt.get_transformed_constraints(m.y, m.outer)
        self.assertEqual(len(cons), 2)
        lb = cons[0]
        assertExpressionsEqual(
            self,
            lb.expr,
            5.0*m.outer_d1.inner_d1.binary_indicator_var +
            5.0*m.outer_d1.inner_d2.binary_indicator_var +
            4*m.outer_d2.binary_indicator_var <= m.y
        )
        ub = cons[1]
        assertExpressionsEqual(
            self,
            ub.expr,
            67*m.outer_d1.inner_d1.binary_indicator_var +
            67*m.outer_d1.inner_d2.binary_indicator_var +
            66.0*m.outer_d2.binary_indicator_var >= m.y
        )
        
        # check that all the y constraints are deactivated, and that the 
        # lower bound ones for x are, but not the upper bound ones
        self.assertFalse(m.outer_d1.c[1].active)
        self.assertFalse(m.outer_d1.c[2].active)
        self.assertFalse(m.outer_d1.inner_d1.c[1].active)
        self.assertFalse(m.outer_d1.inner_d2.c[1].active)
        self.assertTrue(m.outer_d2.c[1].active)
        self.assertFalse(m.outer_d2.c[2].active)
        self.assertFalse(m.outer_d2.c[3].active)

        # and check that there are only four active constraints, the ones we
        # made and the remaining upper bound for x:
        self.assertEqual(len(list(m.component_data_objects(
            Constraint,
            active=True,
            descend_into=(Block, Disjunct)))), 4)
