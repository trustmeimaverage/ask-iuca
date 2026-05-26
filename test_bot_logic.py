import unittest
import os
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class TestBotLogic(unittest.TestCase):
    def setUp(self):
        # We import bot.py inside setUp so any initialization errors are caught
        import bot
        self.bot_mod = bot

    def test_resources_loaded(self):
        # Verify prompt-base and knowledge-base were read and are not empty
        self.assertIsNotNone(self.bot_mod.PROMPT_BASE)
        self.assertIsNotNone(self.bot_mod.KNOWLEDGE_BASE)
        self.assertTrue(len(self.bot_mod.PROMPT_BASE) > 0)
        self.assertTrue(len(self.bot_mod.KNOWLEDGE_BASE) > 0)
        self.assertIn("Ask IUCA", self.bot_mod.PROMPT_BASE)
        self.assertIn("International University of Central Asia", self.bot_mod.KNOWLEDGE_BASE)

    def test_system_prompt_construction(self):
        # Verify 6 variants of system prompts
        for (lang, role), instruction in self.bot_mod.LANG_ROLE_INSTRUCTIONS.items():
            sys_prompt = self.bot_mod.build_system_prompt(lang, role)
            # Must contain prompt-base
            self.assertIn(self.bot_mod.PROMPT_BASE, sys_prompt)
            # Must contain knowledge-base
            self.assertIn(self.bot_mod.KNOWLEDGE_BASE, sys_prompt)
            # Must contain instruction
            self.assertIn(instruction, sys_prompt)
            # Must end with markdown instruction
            self.assertTrue(instruction.endswith("Never use Markdown formatting, asterisks (*), or any special text styling."))

    def test_admin_ids_parsing(self):
        # We can mock ADMIN_IDS or check the current parsing
        # If ADMIN_IDS_STR is empty or template, check it handles it
        self.assertIsInstance(self.bot_mod.ADMIN_IDS, set)

if __name__ == "__main__":
    unittest.main()
