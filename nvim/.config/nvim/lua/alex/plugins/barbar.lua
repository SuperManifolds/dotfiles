return {
  {
    'romgrk/barbar.nvim',
    dependencies = {
      'lewis6991/gitsigns.nvim',      -- OPTIONAL: for git status
      'DaikyXendo/nvim-web-devicons', -- OPTIONAL: for file icons
    },
    init = function() vim.g.barbar_auto_setup = false end,
    opts = {
      -- lazy.nvim will automatically call setup for you. put your options here, anything missing will use the default:
      -- animation = true,
      -- insert_at_start = true,
      -- …etc.
      icons = {
        buffer_index = "superscript",
        filetype = {
          enabled = true
        },
      },
      auto_hide = 1,
    },
    version = '^1.0.0', -- optional: only update when a new 1.x version is released
  }
}
