from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt(name="explain_collection_program")
    def explain_collection_program(program_name: str) -> str:
        """Reusable prompt: explain a Treasury debt collection program in plain language.

        Guides an agent to retrieve authoritative program guidance and synthesize
        a citizen-friendly explanation covering what the program does, who it affects,
        and how it relates to federal receivables.
        """
        return (
            f"Explain the {program_name} program in plain language suitable for a general audience.\n\n"
            f"1. Call search_program_guidance with query='{program_name} program overview authority requirements'.\n"
            "2. Identify: what the program does, what legal authority it operates under, "
            "which agencies use it, and what happens to debtors.\n"
            "3. If the program is TOP, Cross-Servicing, AWG, or CRS, also call "
            "search_program_context to find recent changes or news.\n"
            "4. Write a 2–3 paragraph explanation: first paragraph covers what it is and why it exists, "
            "second covers how it works in practice, third (if relevant) covers recent developments."
        )
