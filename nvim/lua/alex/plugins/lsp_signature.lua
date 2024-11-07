return {
{
  "ray-x/lsp_signature.nvim",
  event = "VeryLazy",
  opts = {
      bind = true,
      transpancy = 20,
      handler_opts = {
          border = "none"
      },
      floating_window_above_cur_line = true
  },
  config = function(_, opts) require'lsp_signature'.setup(opts) end
}
}
