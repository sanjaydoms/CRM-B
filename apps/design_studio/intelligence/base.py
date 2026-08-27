

class DesignIntelligence:
    key = ''

    def generate_queries(self, context, extra_keywords=None):
        raise NotImplementedError

    def rank(self, candidates, context):
        raise NotImplementedError

    def analyse(self, candidate, context=None):
        raise NotImplementedError
