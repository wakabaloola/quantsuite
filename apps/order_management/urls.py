
# Algorithm Trading URLs
from .algorithm_views import AlgorithmicOrderViewSet, AlgorithmExecutionViewSet, CustomStrategyViewSet

# Register algorithm viewsets
router.register(r'algorithmic-orders', AlgorithmicOrderViewSet, basename='algorithmic-orders')
router.register(r'algorithm-executions', AlgorithmExecutionViewSet, basename='algorithm-executions')
router.register(r'custom-strategies', CustomStrategyViewSet, basename='custom-strategies')
