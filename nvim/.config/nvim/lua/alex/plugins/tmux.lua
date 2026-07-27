return {
    {
        'alexghergh/nvim-tmux-navigation',
        opts = {
            disable_when_zoomed = true, -- defaults to false
        },
        keys = {
            { "<C-h>",  function() require('nvim-tmux-navigation').NvimTmuxNavigateLeft() end,       desc = "Tmux nav: left" },
            { "<C-j>",  function() require('nvim-tmux-navigation').NvimTmuxNavigateDown() end,       desc = "Tmux nav: down" },
            { "<C-k>",  function() require('nvim-tmux-navigation').NvimTmuxNavigateUp() end,         desc = "Tmux nav: up" },
            { "<C-l>",  function() require('nvim-tmux-navigation').NvimTmuxNavigateRight() end,      desc = "Tmux nav: right" },
            { "<C-\\>", function() require('nvim-tmux-navigation').NvimTmuxNavigateLastActive() end, desc = "Tmux nav: last active" },
        },
    }
}
