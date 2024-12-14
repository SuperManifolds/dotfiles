return {
	{
		"nvim-neo-tree/neo-tree.nvim",
		branch = "v3.x",
		dependencies = {
			"nvim-lua/plenary.nvim",
			"DaikyXendo/nvim-web-devicons", -- not strictly required, but recommended
			"MunifTanjim/nui.nvim",
			-- "3rd/image.nvim", -- Optional image support in preview window: See `# Preview Mode` for more information
		},
		config = function()
			require("neo-tree").setup({
				close_if_last_window = true,
				enable_git_status = true,
				enable_diagnostics = true,
				filesystem = {
					filtered_items = {
						hide_dotfiles = false
					},
					group_empty_dirs = true,
					use_libuv_file_watcher = true,
				},
				follow_current_file = {
					enabled = true
				},
				group_empty_dirs = true,
				hijack_netrw_behavior = "open_default",
				use_libuv_file_watcher = true,
				source_selector = {
					statusline = true
				},
				window = {
					width = 30,
				},
			})
		end
	}
}
