from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt(name="analyze_agency_performance")
    def analyze_agency_performance(agency_code: str, fiscal_year: int) -> str:
        """Reusable prompt: comprehensive agency receivables performance analysis.

        Guides an agent through a structured analysis combining structured data
        from query_receivables with policy context from search_program_context.
        """
        return (
            f"Provide a comprehensive receivables performance analysis for agency {agency_code} "
            f"in fiscal year {fiscal_year}.\n\n"
            "Steps:\n"
            f"1. Call query_receivables with agency_code='{agency_code}' and fiscal_year={fiscal_year} "
            "to get the structured data.\n"
            "2. Note the delinquency rate and DDR compliance status.\n"
            "3. Call get_delinquency_trends to see how this year compares to the prior 3 years.\n"
            "4. If there is a notable change, call search_program_context with a query about "
            f"'{agency_code} receivables {fiscal_year}' to find policy context.\n"
            "5. Synthesize: present the numbers, the trend direction, and any known policy factors "
            "in a clear summary a financial manager could act on."
        )
