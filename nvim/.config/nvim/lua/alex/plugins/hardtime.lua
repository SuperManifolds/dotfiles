return {
    -- lazy.nvim
    {
        "m4xshen/hardtime.nvim",
        dependencies = { "MunifTanjim/nui.nvim" },
        opts = {
            disabled_keys = {
            },
            hints = {
                ["v%V"] = {
                    message = function()
                        return "Use V instead of vV" -- return the hint message you want to display
                    end,
                    length = 2,                      -- the length of actual key strokes that matches this pattern
                },
                ["$%a"] = {
                    message = function()
                        return "Use A instead of $a" -- return the hint message you want to display
                    end,
                    length = 2,                      -- the length of actual key strokes that matches this pattern
                },
                ["^%i"] = {
                    message = function()
                        return "Use I instead of ^i" -- return the hint message you want to display
                    end,
                    length = 2,                      -- the length of actual key strokes that matches this pattern
                },

            },
        }
    },
}
